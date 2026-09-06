from __future__ import annotations

import argparse
import sys

from satquery.cli import cmd_ask, cmd_inspect, cmd_preprocess, cmd_resolve, cmd_validate


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="satquery")
    sub = parser.add_subparsers(dest="command", required=True)

    p_inspect = sub.add_parser("inspect", help="Print manifest + modality inference for a raster file")
    p_inspect.add_argument("path")

    p_validate = sub.add_parser("validate", help="Validate a pair of rasters for co-registration and cross-modal compatibility")
    p_validate.add_argument("path_a", help="reference image")
    p_validate.add_argument("path_b", help="candidate image, checked against path_a")

    p_preprocess = sub.add_parser("preprocess", help="Render a raster to a viewable PNG (SAR dB-stretch or optical band selection)")
    p_preprocess.add_argument("path")
    p_preprocess.add_argument("--out", default=None, help="output PNG path (default: <path>.preview.png)")

    p_resolve = sub.add_parser("resolve", help="Resolve which registered tool handles a capability/modality/image-count query")
    p_resolve.add_argument("--capability", required=True, choices=["vqa", "captioning", "grounding", "change_detection", "cross_modal_fusion"])
    p_resolve.add_argument("--modalities", required=True, nargs="+", choices=["sar", "optical_rgb", "optical_ms"])
    p_resolve.add_argument("--image-count", required=True, type=int)

    p_ask = sub.add_parser("ask", help="Run the full 9-node agent pipeline over a question and 1-2 images, printing a JSON trace")
    p_ask.add_argument("question")
    p_ask.add_argument("images", nargs="+", help="1 or 2 image paths")

    args = parser.parse_args(argv)

    if args.command == "inspect":
        cmd_inspect(args.path)
    elif args.command == "validate":
        report = cmd_validate(args.path_a, args.path_b)
        sys.exit(0 if report.ok else 1)
    elif args.command == "preprocess":
        cmd_preprocess(args.path, args.out)
    elif args.command == "resolve":
        result = cmd_resolve(args.capability, args.modalities, args.image_count)
        sys.exit(0 if result.chosen is not None else 1)
    elif args.command == "ask":
        state = cmd_ask(args.question, args.images)
        sys.exit(0 if state.outcome == "answered" else 1)


if __name__ == "__main__":
    main()
