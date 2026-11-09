"""Compatibility command for the canonical journal schematics."""
import argparse
from pathlib import Path

from figure_style import paper_style
from publication_figures import epochs, pipeline, veto, lower


def draw(out):
    paper_style('tpds')
    for fn in (epochs, pipeline, veto, lower):
        fn(out,None)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parent)
    draw(parser.parse_args().output)
