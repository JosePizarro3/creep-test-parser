from decouple import config as environ
from pybis import Openbis

# Connect to openBIS
# Add a file in your home directory named `.env` with the following content:
# OPENBIS_URL=your_openbis_url
# OPENBIS_USERNAME=your_username
# OPENBIS_PASSWORD=your_password
openbis = Openbis(environ("OPENBIS_URL"))
openbis.login(environ("OPENBIS_USERNAME"), environ("OPENBIS_PASSWORD"), save_token=True)


from bam_masterdata.cli.run_parser import run_parser

from creep_test_parser.parser import CreepTestParser

# Define which parser to use and which files to parse
files_parser = {
    CreepTestParser(): [
        "./tests/data/test.xlsx",
    ]
}

# Run the parser
run_parser(
    openbis=openbis,
    space_name="VP.1_JPIZARRO",
    project_name="CREEPTEST_PROJECT",
    collection_name="CREEPTEST_TEST_COLLECTION",
    files_parser=files_parser,
)
print("Parsing completed.")
