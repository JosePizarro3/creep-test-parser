import re
from abc import ABC, abstractmethod

import pandas as pd
from bam_masterdata.datamodel.object_types import ExperimentalStep
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
    # the object types of this case do not exist yet in bam_masterdata.datamodel.object_types
    def parse(self, files, collection, logger):
        for file in files:
            if not file.endswith(".xlsx"):
                logger.error(f"CreepTestParser: Unsupported file type {file}")
                continue

            df = ExcelParser(file).custom_parser()

            # first object entry
            for key, value in df.items():
                print(f"Processing sheet: {key}")  # logger later
                df = value.head(5)  # 5 rows for the object
                # optional cleanup of columns
                df.columns = (
                    df.columns.str.strip()
                    .str.lower()
                    .str.replace(" ", "_")
                    .str.replace("/", "_")
                )
                parsed = {}
                # filter relevant columns
                df_parsed = df[
                    [
                        "category_i",
                        "category_ii",
                        "category_iii",
                        "entry",
                        "data_type",
                        "requirement",
                        "answer___options",
                    ]
                ].copy()
                # extract relevant info
                for _, row in df_parsed.iterrows():
                    key = row["entry"]

                    parsed[key] = {
                        "category": row["category_i"],
                        "sub_category": row["category_ii"],
                        "group": row["category_iii"],
                        "data_type": row["data_type"],
                        "requirement": row["requirement"],
                        "answer/options": row["answer___options"],
                    }
                # mapping example
                Experiment = ExperimentalStep(
                    code=parsed["Test ID"]["answer/options"],
                    name=parsed["Project"]["answer/options"],
                    start_date=parsed["Date of test start"]["answer/options"],
                    end_date=parsed["Data of test end"]["answer/options"],
                )
                print(Experiment)
            # later add to collection / add relations
            # continue with next rows in "value" dataframe
