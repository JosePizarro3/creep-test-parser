from .parser import CreepTestParser

# Add more metadata if needed
creep_test_parser_entry_point = {
    "name": "CreepTestParser",
    "description": "An openBIS parser for creep testing data in BAM.",
    "parser_class": CreepTestParser,
}
