"""CLI entry point for tldr.

Usage:
    # From any directory:
    uv run python -m tldr analyze --source-root <path/to/sources> --input-dir <path/to/workspace>

    # Explicit paths:
    uv run python -m tldr analyze --input-dir /path/to/tld-workspace --source-root /path/to/src
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import run_pipeline, write_output


def _run_analyze(args: argparse.Namespace) -> None:
    # Resolve input directory
    input_dir = args.input_dir
    if not (input_dir / "groups.yaml").exists():
        if (Path.cwd() / "groups.yaml").exists():
            input_dir = Path.cwd()
        else:
            print(
                f"ERROR: groups.yaml not found in {input_dir} or {Path.cwd()}.\n"
                "  Specify --input-dir pointing to the tld workspace directory.",
                file=sys.stderr,
            )
            sys.exit(1)

    output_dir = args.output_dir or input_dir

    source_root = args.source_root.resolve()

    # Resolve repo root
    if args.repo_root:
        repo_root = args.repo_root.resolve()
    else:
        # Walk up from source_root to find .git
        candidate = source_root
        while candidate != candidate.parent:
            if (candidate / ".git").exists():
                repo_root = candidate
                break
            candidate = candidate.parent
        else:
            print("ERROR: Cannot detect repo root. Provide --repo-root.", file=sys.stderr)
            sys.exit(1)

    # Default exclusions
    exclude_patterns = [
        "**/*Test.kt",
        "**/test/**",
        "**/androidDeviceTest/**",
        "**/androidHostTest/**",
        "**/iosTest/**",
        "**/commonTest/**",
        "**/build/**",
        "**/generated/**",
        "**/*.kts",
    ]

    # Run pipeline
    result = run_pipeline(
        input_dir=input_dir,
        source_root=source_root,
        repo_root=repo_root,
        max_group_size=args.max_group_size,
        all_classes=args.all_classes,
        exclude_patterns=exclude_patterns,
    )

    # Write output
    if args.dry_run:
        print("\n[DRY RUN] No files written.")
    else:
        write_output(result, output_dir)


def _run_serve(args: argparse.Namespace) -> None:
    from .server import serve

    if args.frontend_dist is not None:
        frontend_dist = args.frontend_dist.resolve()
    else:
        # Default to the frontend bundled inside the installed package
        frontend_dist = Path(__file__).parent / "_frontend"
        if not frontend_dist.exists():
            print(
                "ERROR: No bundled frontend found and --frontend-dist was not provided.\n"
                "Either install from PyPI (which bundles the frontend) or pass --frontend-dist.",
                file=__import__("sys").stderr,
            )
            __import__("sys").exit(1)

    serve(
        workspace=args.workspace.resolve(),
        frontend_dist=frontend_dist,
        port=args.port,
        open_browser=not args.no_open,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze Kotlin sources and generate navigable architecture diagrams.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- analyze subcommand ---
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze Kotlin sources and emit elements/connectors YAML.",
    )
    analyze_parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent.parent,  # src/../.. = workspace root
        help="Directory containing groups.yaml (default: workspace root)",
    )
    analyze_parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory (defaults to input-dir)",
    )
    analyze_parser.add_argument(
        "--source-root",
        type=Path,
        required=True,
        help="Kotlin source directory to analyze",
    )
    analyze_parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Repository root (default: auto-detect via .git)",
    )
    analyze_parser.add_argument(
        "--max-group-size",
        type=int,
        default=None,
        help="Maximum elements per group before auto-splitting (default: 20, 0=disabled)",
    )
    analyze_parser.add_argument(
        "--all-classes",
        action="store_true",
        help="Keep all classes (default: only classes participating in connectors)",
    )
    analyze_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print stats without writing files",
    )

    # --- serve subcommand ---
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start the diagram viewer server.",
    )
    serve_parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="Directory containing elements.yaml and connectors.yaml",
    )
    serve_parser.add_argument(
        "--frontend-dist",
        type=Path,
        default=None,
        help="Path to the built frontend dist/ (default: bundled with package)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8060,
        help="Port to listen on (default: 8060)",
    )
    serve_parser.add_argument(
        "--no-open",
        action="store_true",
        help="Skip opening the browser",
    )

    args = parser.parse_args()

    # Backward compat: no subcommand → analyze (requires --source-root to be explicit)
    if args.command is None or args.command == "analyze":
        if args.command is None:
            # Re-parse under analyze to get defaults/required validation
            analyze_parser.parse_args(sys.argv[1:], namespace=args)
        _run_analyze(args)
    elif args.command == "serve":
        _run_serve(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
