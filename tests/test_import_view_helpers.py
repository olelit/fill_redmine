from dto.import_action import ImportAction


def test_action_labels_are_human_readable():
    assert ImportAction.REDMINE_FILL.label == "Redmine"
    assert ImportAction.YOUTRACK_TRANSFER.label == "YouTrack → Redmine"


def test_action_values_are_stable():
    assert ImportAction.REDMINE_FILL.value == "redmine_fill"
    assert ImportAction.YOUTRACK_TRANSFER.value == "youtrack_transfer"
