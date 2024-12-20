from pathlib import Path

import pytest
from src.get_charm_paths import find_charms_in_dir

EXPECTED_RESULTS = [
    ("./charms_dir_no_charms/", [Path("./charms_dir_no_charms/")]),
    ("./base_dir_overrided_by_charm/",
     [Path("./base_dir_overrided_by_charm/charms/charm1/")]),
    ("./single_charm_dir/", [Path("./single_charm_dir/")]),
    ("./multi_charm_with_charms/",
     [Path("./multi_charm_with_charms/charms/charm0/"),
      Path("./multi_charm_with_charms/charms/charm1/")]),
    ("./multi_charm_without_charms/", []),
    ("./charms_not_in_correct_subdir", []),
    ("./single_charm_dir_charmcraft", [Path("./single_charm_dir_charmcraft")]),
    ("./multi_charm_charmcraft/",
     [Path("./multi_charm_charmcraft/charms/charm0/"),
      Path("./multi_charm_charmcraft/charms/charm1/")]),
]


@pytest.mark.parametrize("base_dir, expected", EXPECTED_RESULTS)
def test_find_charms_in_subdirs(base_dir, expected):
    charm_dirs = find_charms_in_dir(base_dir)
    assert charm_dirs == expected
