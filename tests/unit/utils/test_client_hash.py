from nisar_hazard_watch.constants.limits import CLIENT_KEY_LENGTH
from nisar_hazard_watch.utils.client_hash import hash_client_key

ADDRESS = "203.0.113.7"
OTHER_ADDRESS = "203.0.113.8"


def test_a_client_is_stored_as_a_fixed_length_digest_that_does_not_contain_its_address() -> None:
    # Arrange
    address = ADDRESS

    # Act
    digest = hash_client_key(client=address)

    # Assert
    assert len(digest) == CLIENT_KEY_LENGTH
    assert address not in digest


def test_the_same_client_always_gets_the_same_digest_and_two_clients_differ() -> None:
    # Arrange
    first, second = ADDRESS, OTHER_ADDRESS

    # Act
    digests = (
        hash_client_key(client=first),
        hash_client_key(client=first),
        hash_client_key(client=second),
    )

    # Assert
    assert digests[0] == digests[1]
    assert digests[0] != digests[2]
