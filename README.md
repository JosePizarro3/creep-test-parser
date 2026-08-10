# BAM Creep Test Parser

An openBIS parser for creep testing data in BAM.

A tutorial in `tutorials/parser_tutorial.py` help parsing the Creep Excel files into the BAM openBIS instance. This tutorial uses the parser class defined in `src/creep_test_parser/parser.py` and the [`bam-masterdata`](https://github.com/BAMresearch/bam-masterdata) parser infrastructure.

## Development

If you want to develop locally this package, clone the project and enter in the workspace folder:

```bash
git clone https://github.com/BAMresearch/creep-test-parser.git
cd creep-test-parser
```

Create a virtual environment (you can use Python>=3.10) in your workspace:

- **Using venv**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate  # in Windows (cmd): source .venv\Scripts\activate
  ```
- **Using conda**:
  ```bash
  conda create --name .venv pip
  conda activate .venv
  ```

Install the package in editable mode (with the flag `-e`):
```bash
pip install --upgrade pip
pip install -e '.[dev]'
```

**Note**: In order to install faster the package, you can use [`uv`](https://docs.astral.sh/uv/) for pip installing Python packages:
```bash
pip install --upgrade pip
pip install uv
uv pip install -e '.[dev]'
```


### Run the tests

You can locally run the tests by doing:

```bash
python -m pytest -sv tests
```

where the `-s` and `-v` options toggle the output verbosity.

You can also generate a local coverage report:

```bash
python -m pytest --cov=src tests
```

### Run auto-formatting and linting

We use [Ruff](https://docs.astral.sh/ruff/) for formatting and linting the code following the rules specified in the `pyproject.toml`. You can run locally:

```bash
ruff check .
```

This will produce an output with the specific issues found. In order to auto-fix them, run:

```bash
ruff format .
```

If some issues are not possible to fix automatically, you will need to visit the file and fix them by hand.
