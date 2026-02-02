from pathlib import Path

from bam_masterdata.logger import logger
from bam_masterdata.metadata.entities import CollectionType

from src.creep_test_parser.parser import CreepTestParser


class TestCreepTestParser:
    def test_parse(self):
        parser = CreepTestParser()
        collection = CollectionType()
        test_file = Path(__file__).parent / "test.xlsx"
        parser.parse([str(test_file)], collection, logger)
        assert collection is not None
        assert len(collection.attached_objects) == 1
        assert len(collection.relationships) == 0
        objects = list(collection.attached_objects.values())
        assert objects[0].name == "Project Name"
        assert objects[0].name != "Some Other Name"
