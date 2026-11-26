"""audioconverter: Audio Converter 백엔드."""

__version__ = "1.0.0"


def main() -> None:
    from audioconverter.cli import main as cli_main

    cli_main()
