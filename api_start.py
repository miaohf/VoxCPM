"""VoxCPM OpenAI-compatible API server launcher."""

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Start VoxCPM OpenAI-compatible API server")
    parser.add_argument("--host", type=str, default=None, help="Listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="Listen port (default: 8808)")
    parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated allowed model IDs (default: openbmb/VoxCPM2)",
    )
    parser.add_argument(
        "--voices-dir",
        type=str,
        default=None,
        help="Local voice reference directory (default: assets/voices)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="SQLite path for voice metadata (default: data/voices.sqlite)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="API log level (default: INFO)",
    )
    args = parser.parse_args()

    if args.host is not None:
        os.environ["HOST"] = args.host
    if args.port is not None:
        os.environ["PORT"] = str(args.port)
    if args.models is not None:
        os.environ["ALLOWED_MODELS"] = args.models
    if args.voices_dir is not None:
        os.environ["VOICE_REFERENCES_DIR"] = args.voices_dir
    if args.db_path is not None:
        os.environ["VOICES_DB_PATH"] = args.db_path
    if args.log_level is not None:
        os.environ["LOG_LEVEL"] = args.log_level

    from api.config import get_host, get_port

    host = get_host()
    port = get_port()
    print(f"Starting VoxCPM API at http://{host}:{port}")
    uvicorn.run("api.main:app", host=host, port=port)


if __name__ == "__main__":
    main()
