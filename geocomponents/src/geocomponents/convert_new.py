from geocomponents.descriptions.models import DomainDef


def _validate_domain(domain: dict) -> None:
    validated_model = DomainDef.model_validate(domain)
    if validated_model:
        print("Domain validated successfully.")  # noqa: T201


def _cli_main() -> None:  # pragma: no cover
    import argparse
    from pathlib import Path

    import yaml

    parser = argparse.ArgumentParser(
        description="Convert a QMS JSON schema to a geocomponents dataset YAML."
    )
    parser.add_argument("--uml", required=True, type=Path, help="QMS JSON input file")
    parser.add_argument(
        "--domain", required=True, type=Path, help="Domain YAML input file"
    )
    parser.add_argument("--output", required=True, type=Path, help="YAML output file")
    parser.add_argument(
        "--dataset-name", required=True, help="Dataset identifier (SafeIdentifier)"
    )

    args = parser.parse_args()

    domain = yaml.safe_load(args.domain.read_text(encoding="utf-8"))
    _validate_domain(domain)


if __name__ == "__main__":  # pragma: no cover
    _cli_main()
