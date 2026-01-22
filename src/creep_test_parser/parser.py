from abc import ABC, abstractmethod

import pandas as pd

# from bam_masterdata.datamodel.object_types import ExperimentalStep
from bam_masterdata.parsing import AbstractParser


class BaseFileParser(ABC):
    @abstractmethod
    def custom_parser(self):
        pass


class ExcelParser(BaseFileParser):
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
    def parse(self, files, collection, logger):
        for file in files:
            if not file.endswith(".xlsx"):
                logger.error(f"CreepTestParser: Unsupported file type {file}")
                continue

            df = ExcelParser(file).custom_parser()
            # map into openBIS object types
            # ...
