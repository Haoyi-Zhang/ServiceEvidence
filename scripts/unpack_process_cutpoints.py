"""Independent standard-ZIP audit unpacker; validates bytes before writing.

No code from the archive is executed. The one transport-only RAW-FILES.json
indexes every original file; originals are restored exactly, including empty
files and interrupted temporary snapshots. No overwrite or symlink extraction.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,stat,zipfile

def require(ok,message):
    if not ok:raise ValueError(message)

def unpack(archive,output,expected_sha256=None):
    output=Path(output);require(not output.exists(),'Fresh owned output directory required')
    if expected_sha256 is not None:require(hashlib.sha256(Path(archive).read_bytes()).hexdigest()==expected_sha256,'Published archive SHA mismatch')
    files={};portable=set();total=0
    with zipfile.ZipFile(archive) as bundle:
        members=bundle.infolist();require(len(members)<=200,'Archive member bound')
        for member in members:
            name=member.filename;path=PurePosixPath(name)
            require(member.orig_filename==name and '\0' not in name and name not in files and name.casefold() not in portable,'Duplicate/truncated member name')
            require(not path.is_absolute() and '..' not in path.parts and '\\' not in name and ':' not in name and path.as_posix()==name,'Unsafe relative member')
            require(member.create_system==3 and member.external_attr>>16==stat.S_IFREG|0o644 and not member.flag_bits&1,'Only unencrypted regular0644files accepted')
            require(not member.is_dir() and member.file_size<=2*1024**2,'File kind/size bound')
            total+=member.file_size;require(total<=20*1024**2,'Total expanded-byte bound')
            files[name]=bundle.read(member);portable.add(name.casefold())
    require('RAW-FILES.json' in files,'Missing transport file manifest')
    manifest_bytes=files.pop('RAW-FILES.json');manifest=json.loads(manifest_bytes)
    rows=manifest['files'];expected={row['path']:row for row in rows}
    require(len(rows)==len(expected)==141 and set(files)==set(expected),'Exact original141file inventory required')
    require(sum(len(data) for data in files.values())==manifest['total_bytes'],'Expanded original-byte count differs')
    for name,data in files.items():
        row=expected[name]
        require(type(row['bytes']) is int and len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'Original-byte SHA/length mismatch: '+name)
    # No output exists until all member/path/kind/byte/inventory checks pass.
    output.mkdir(parents=True)
    for name,data in sorted(files.items()):
        target=output/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    return dict(original_files=len(files),original_bytes=manifest['total_bytes'],all_original_bytes_verified=True,
                transport_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                note='Transport-only manifest not an additional scientific observation; no new process run')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--sha256');a=p.parse_args()
    print(json.dumps(unpack(a.archive,a.out,a.sha256),sort_keys=True))
