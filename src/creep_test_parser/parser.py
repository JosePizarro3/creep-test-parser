import re
from abc import ABC, abstractmethod

import pandas as pd
from bam_masterdata.datamodel.object_types import ExperimentalStep
from bam_masterdata.logger import logger
from bam_masterdata.metadata.entities import CollectionType
from bam_masterdata.parsing import AbstractParser


class BaseFileParser(ABC):
    @abstractmethod
    def custom_parser(self):
        pass


class ExcelParser(BaseFileParser):
    # this class could handle excel parsing + custom parsing depending on the file format (like this example)
    #
    # this means that, this class (and `BaseFileParser`) should be in bam_masterdata.parsing module instead, and here
    # we just overwrite `custom_parser()` method for our specific case
    # Then, the BaseFileParser could be a layer to handle different file types (csv, json, xml, etc) if needed in the future
    # and ExcelParser would handle only excel files (note: BaseFileParser might be an interface (i.e., a plain class) instead of an abstract class)
    def __init__(self, filepath: str):
        self.filepath = filepath

    def custom_parser(self):
        df_source = pd.read_excel(
            self.filepath, sheet_name=None, header=0, engine="openpyxl", dtype=str
        )
        # row index where the real header lives
        header_row = 6

        new_df = {}
        for key, df in df_source.items():
            # filter tabs
            if re.search(
                r"(Test|Schema|Chemical|Data|Measurement)", key, flags=re.IGNORECASE
            ):
                continue
            # extract header
            new_header = df.iloc[header_row]

            # slice data below header
            df = df.iloc[header_row + 1 :].copy()

            # assign header
            df.columns = new_header
            # cleanup
            new_df[key] = df.reset_index(drop=True)

        return new_df


class CreepTestParser(AbstractParser):
    def __init__(self):
        self.object_mappings = {"Test job details": ExperimentalStep}
        self.value_mappings = {
            "Date of test start": "start_date",
            "Data of test end": "end_date",
            "Project": "name",
            "Test ID": "code",
        }

    # the object types of this case do not exist yet in bam_masterdata.datamodel.object_types
    def parse(
        self, files: list[str], collection: CollectionType, logger=logger
    ) -> None:
        for file in files:
            if not file.endswith(".xlsx"):
                logger.error(f"CreepTestParser: Unsupported file type {file}")
                continue

            df = ExcelParser(file).custom_parser()

            # first object entry
            for key, value in df.items():
                logger.info(f"Processing sheet: {key}")
                df = value

                # optional cleanup of columns
                df.columns = (
                    df.columns.str.strip()
                    .str.lower()
                    .str.replace(" ", "_")
                    .str.replace("/", "_")
                )

                # filter relevant columns
                df_parsed = df[
                    [
                        "category_iii",
                        "entry",
                        "data_type",
                        "requirement",
                        "answer___options",
                    ]
                ].copy()

                # Group by category_iii to structure the data
                result = {}
                for category, group in df_parsed.groupby("category_iii"):
                    result[category] = {
                        row["entry"]: [
                            row["data_type"],
                            row["requirement"],
                            row["answer___options"],
                        ]
                        for _, row in group.iterrows()
                    }

                object_ids = []
                # mapping example
                for mapping_key, object_type in result.items():
                    if mapping_key not in self.object_mappings:
                        continue
                    object = self.object_mappings[mapping_key]()
                    for field, attributes in object_type.items():
                        if field in self.value_mappings:
                            setattr(
                                object,
                                self.value_mappings[field],
                                attributes[
                                    2
                                ],  # assuming answer___options is the value, later for unit/symbols this needs to be adjusted
                            )
                    object_id = collection.add(object)
                    object_ids.append(object_id)
