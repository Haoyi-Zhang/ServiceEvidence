import asyncio
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cie.model import EvidenceCell, Replica, Vote
from cie.service import Service, WireStats, pack, rpc


class ServiceDurabilityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.snapshot = Path(self.temporary.name) / "state.json"
        self.sources = ["v0", "v1"]
        self.members = ["n0"]

    def service(self, *, stats=None):
        return Service(
            "n0",
            self.sources,
            1,
            [],
            self.members,
            self.snapshot,
            stats=stats,
        )

    @staticmethod
    def cell(left="a", right="b", epoch=0, source="v0", vote=Vote.SAME):
        return EvidenceCell(left, right, epoch, source, vote, "durability-test")

    async def ingest(self, service, *cells):
        return await service.dispatch(
            {"op": "ingest", "cells": [cell.to_dict() for cell in cells]}
        )

    async def test_replace_failure_preserves_memory_and_previous_snapshot(self):
        service = self.service()
        await self.ingest(service, self.cell())
        before_memory = service.replica.export_state()
        before_disk = self.snapshot.read_text(encoding="utf-8")

        with patch("cie.service.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                await self.ingest(service, self.cell("c", "d"))

        self.assertEqual(service.replica.export_state(), before_memory)
        self.assertEqual(self.snapshot.read_text(encoding="utf-8"), before_disk)
        self.assertFalse(self.snapshot.with_suffix(".pending").exists())

    async def test_directory_fsync_failure_has_idempotent_ambiguous_outcome(self):
        stats = WireStats()
        service = self.service(stats=stats)
        cell = self.cell()

        with patch("cie.service.fsync_directory", side_effect=OSError("directory fsync failed")):
            with self.assertRaises(OSError):
                await self.ingest(service, cell)

        # Replace already succeeded.  The RPC is unacknowledged, but the live
        # process and the visible snapshot agree; retrying the immutable cell is
        # idempotent rather than duplicating evidence.
        self.assertEqual(len(service.replica), 1)
        saved = json.loads(self.snapshot.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["cells"]), 1)
        self.assertEqual(stats.commits, 0)
        self.assertFalse(self.snapshot.with_suffix(".pending").exists())

        result = await self.ingest(service, cell)
        self.assertEqual(result["cells"], 1)
        self.assertEqual(stats.commits, 1)
        restarted = self.service()
        self.assertEqual(restarted.replica.export_state(), service.replica.export_state())

    async def test_concurrent_ingests_serialize_without_lost_update(self):
        service = self.service()
        cells = [
            self.cell(f"h{2 * index:02d}", f"h{2 * index + 1:02d}")
            for index in range(20)
        ]
        await asyncio.gather(*(self.ingest(service, cell) for cell in cells))
        self.assertEqual(len(service.replica), len(cells))
        restarted = self.service()
        self.assertEqual(restarted.replica.export_state(), service.replica.export_state())

    async def test_acknowledgement_is_read_only(self):
        stats = WireStats()
        service = self.service(stats=stats)
        await self.ingest(
            service,
            self.cell(source="v0"),
            self.cell(source="v1", vote=Vote.UNKNOWN),
        )
        before = self.snapshot.read_text(encoding="utf-8")
        commits = stats.commits
        answer = await service.dispatch({"op": "ack", "floors": [["a", "b", 0]]})
        self.assertEqual(answer["member"], "n0")
        self.assertEqual(len(answer["vectors"]), 2)
        self.assertEqual(stats.commits, commits)
        self.assertEqual(self.snapshot.read_text(encoding="utf-8"), before)

    async def test_floor_ack_retries_indeterminate_durability_before_retirement(self):
        stats = WireStats()
        service = self.service(stats=stats)
        vector = (self.cell(source="v0"), self.cell(source="v1", vote=Vote.UNKNOWN))
        request = {"op": "ack", "floors": [["a", "b", 0]]}
        with patch("cie.service.fsync_directory", side_effect=OSError("directory fsync failed")):
            with self.assertRaises(OSError):
                await self.ingest(service, *vector)
            # Seeing the vector in memory is not a durable acknowledgement.
            with self.assertRaises(OSError):
                await service.dispatch(request)
        ack = await service.dispatch(request)
        self.assertEqual(stats.commits, 1)
        self.assertEqual(len(ack["vectors"]), 2)
        restarted = self.service()
        self.assertEqual(restarted.replica.export_state(), service.replica.export_state())
        before = stats.commits
        await service.dispatch(request)
        self.assertEqual(stats.commits, before)  # Ordinary durable ack stays read-only.

    async def test_reopened_visible_snapshot_needs_floor_ack_barrier(self):
        service = self.service()
        with patch("cie.service.fsync_directory", side_effect=OSError("directory fsync failed")):
            with self.assertRaises(OSError):
                await self.ingest(service, self.cell(source="v0"),
                                  self.cell(source="v1", vote=Vote.UNKNOWN))
        stats = WireStats()
        restarted = self.service(stats=stats)
        request = {"op": "ack", "floors": [["a", "b", 0]]}
        with patch("cie.service.fsync_directory", side_effect=OSError("still failing")):
            with self.assertRaises(OSError):
                await restarted.dispatch(request)
        self.assertEqual(stats.commits, 0)
        await restarted.dispatch(request)
        self.assertEqual(stats.commits, 1)
        await restarted.dispatch(request)
        self.assertEqual(stats.commits, 1)


    async def test_rpc_does_not_hang_when_peer_close_never_completes(self):
        reader = asyncio.StreamReader()
        reader.feed_data(pack({"ok": True, "result": {"value": 7}}))
        reader.feed_eof()

        class HangingWriter:
            def __init__(self):
                self.closed = False

            def write(self, _payload):
                return None

            async def drain(self):
                return None

            def close(self):
                self.closed = True

            async def wait_closed(self):
                await asyncio.sleep(60)

        writer = HangingWriter()
        with patch("cie.service.asyncio.open_connection", return_value=(reader, writer)), \
             patch("cie.service.RPC_TIMEOUT", 0.01):
            answer = await rpc(1, {"op": "state"})
        self.assertEqual(answer, {"value": 7})
        self.assertTrue(writer.closed)

    async def test_unacknowledged_pending_file_is_discarded_on_restart(self):
        service = self.service()
        await self.ingest(service, self.cell())
        pending = self.snapshot.with_suffix(".pending")
        pending.write_text('{"incomplete":', encoding="utf-8")
        restarted = self.service()
        self.assertFalse(pending.exists())
        self.assertEqual(restarted.replica.export_state(), service.replica.export_state())


class AcknowledgementSchemaTests(unittest.IsolatedAsyncioTestCase):
    """Memory-only protocol controls; no constructor, files, sockets or fsync."""

    async def fixture(self, pending=False):
        service = Service.__new__(Service)
        service.members = ("n0", "n1")
        service.replica = Replica("n0", ["v0", "v1"], 1, ["a", "b"])
        service._durability_pending = False
        for epoch in (0, 1):
            for source in service.replica.sources:
                service.replica.add(EvidenceCell(
                    "a", "b", epoch, source, Vote.SAME, "owned schema control"
                ))
        floors = [["a", "b", 1]]
        with patch.object(service, "_commit", side_effect=AssertionError("unexpected commit")) as commit:
            ack = await service.dispatch({"op": "ack", "floors": floors})
            commit.assert_not_called()
        remote = copy.deepcopy(ack)
        remote["member"] = "n1"
        service._durability_pending = pending
        return service, {"op": "compact", "floors": floors, "acks": [ack, remote], "pending": 0}

    async def assert_rejected_before_commit(self, change):
        for pending in (False, True):
            with self.subTest(durability_pending=pending):
                service, request = await self.fixture(pending)
                change(request)
                before = service.replica.export_state()
                original_request = copy.deepcopy(request)
                with patch.object(service, "_commit", side_effect=AssertionError("unexpected commit")) as commit:
                    with self.assertRaises(ValueError):
                        await service.dispatch(request)
                    commit.assert_not_called()
                self.assertEqual(service.replica.export_state(), before)
                self.assertIs(service._durability_pending, pending)
                self.assertEqual(request, original_request)

    async def test_float_and_boolean_epochs_refuse_before_any_commit(self):
        for value in (1.0, True):
            for field in ("floor", "cell"):
                with self.subTest(value=value, field=field):
                    def change(request):
                        ack = request["acks"][1]
                        if field == "floor":
                            ack["floors"][0][2] = value
                        else:
                            ack["vectors"][0]["epoch"] = value
                    await self.assert_rejected_before_commit(change)

    async def test_missing_and_extra_ack_or_cell_fields_refuse(self):
        for field in ("member", "floors", "vectors"):
            with self.subTest(missing_ack_field=field):
                await self.assert_rejected_before_commit(lambda r: r["acks"][1].pop(field))
        for field in ("left", "right", "epoch", "source", "vote", "reason"):
            with self.subTest(missing_cell_field=field):
                await self.assert_rejected_before_commit(lambda r: r["acks"][1]["vectors"][0].pop(field))
        await self.assert_rejected_before_commit(
            lambda r: r["acks"][1].update(stable_floors=[["a", "b", 0]])
        )
        await self.assert_rejected_before_commit(
            lambda r: r["acks"][1]["vectors"][0].update(selected_epoch=0)
        )
        await self.assert_rejected_before_commit(
            lambda r: r["acks"][1]["floors"][0].append(0)
        )

    async def test_malformed_nested_types_refuse(self):
        for field, value in (("member", 1), ("floors", {}), ("vectors", {}), ("vectors", None)):
            with self.subTest(field=field, value=value):
                await self.assert_rejected_before_commit(lambda r: r["acks"][1].update({field: value}))
        for field, value in (("source", True), ("vote", True), ("reason", 0), ("left", None)):
            with self.subTest(cell_field=field, value=value):
                await self.assert_rejected_before_commit(
                    lambda r: r["acks"][1]["vectors"][0].update({field: value})
                )

    async def test_incomplete_conflicting_and_wrong_member_acks_refuse(self):
        changes = (
            lambda r: r["acks"][1]["vectors"].pop(),
            lambda r: r["acks"][1]["vectors"].append(copy.deepcopy(r["acks"][1]["vectors"][0])),
            lambda r: r["acks"][1]["vectors"][0].update(vote="different"),
            lambda r: r["acks"][1]["vectors"][0].update(reason="contradictory reason"),
            lambda r: r["acks"][1]["floors"][0].__setitem__(2, 0),
            lambda r: r["acks"][1].update(member="n0"),
            lambda r: r["acks"][1].update(member="foreign"),
        )
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                await self.assert_rejected_before_commit(change)

    async def test_legal_ack_compacts_with_pending_barrier_preserved(self):
        for pending in (False, True):
            with self.subTest(durability_pending=pending):
                service, request = await self.fixture(pending)
                # JSON object-key and member order are not semantic differences.
                request["acks"].reverse()
                for ack in request["acks"]:
                    ack["vectors"] = [dict(reversed(list(cell.items()))) for cell in ack["vectors"]]
                request["acks"] = [dict(reversed(list(ack.items()))) for ack in request["acks"]]
                original_request = copy.deepcopy(request)
                published = []

                def memory_commit(proposed):
                    published.append(proposed.export_state())
                    service.replica = proposed
                    service._durability_pending = False

                with patch.object(service, "_commit", side_effect=memory_commit) as commit:
                    result = await service.dispatch(request)
                    self.assertEqual(commit.call_count, 2 if pending else 1)
                self.assertEqual(result, {"removed": 2, "cells": 2})
                self.assertEqual(service.replica.stable_floors, {("a", "b"): 1})
                self.assertTrue(all(cell.epoch == 1 for cell in service.replica.cells))
                if pending:
                    self.assertEqual(len(published[0]["cells"]), 4)
                    self.assertEqual(published[0]["stable_floors"], [])
                self.assertEqual(request, original_request)

    async def test_pending_barrier_failure_does_not_publish_compacted_state(self):
        service, request = await self.fixture(pending=True)
        before = service.replica.export_state()
        with patch.object(service, "_commit", side_effect=OSError("owned barrier failure")) as commit:
            with self.assertRaises(OSError):
                await service.dispatch(request)
            commit.assert_called_once_with(service.replica)
        self.assertEqual(service.replica.export_state(), before)
        self.assertTrue(service._durability_pending)

    async def test_invalid_pending_allowance_refuses_before_barrier(self):
        for value in (True, 0.0, -1, "0"):
            with self.subTest(pending=value):
                await self.assert_rejected_before_commit(lambda r: r.update(pending=value))


if __name__ == "__main__":
    unittest.main()
