import glob
import os
from os import mkdir
from os.path import exists
from typing import List

import click
import yaml
from web3 import Web3

from encoder import Decoder
from database import Database, check_db_connection
from utils import is_lists_equal
from validators import validate_db_uri, validate_env_name

DECRYPTION_KEY_ENV = "DECRYPTION_KEY"


@click.command(help="Synchronizes web3signer private keys from the database")
@click.option(
    "--db-url",
    help="The database connection address.",
    required=True,
    callback=validate_db_uri,
)
@click.option(
    "--output-dir",
    help="The folder where web3signer keystores will be saved.",
    required=True,
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
)
@click.option(
    "--decryption-key-env",
    help="The environment variable with the decryption key for private keys in the database.",
    default=DECRYPTION_KEY_ENV,
    callback=validate_env_name,
)
def sync_web3signer_keys(db_url: str, output_dir: str, decryption_key_env: str) -> None:
    """
    The command is running by the init container in web3signer pods.
    Fetch and decrypt keys for web3signer and store them as keypairs in the output_dir.
    """
    check_db_connection(db_url)

    database = Database(db_url=db_url)
    keys_records = database.fetch_keys()

    # decrypt private keys
    decryption_key = os.environ[decryption_key_env]
    decoder = Decoder(decryption_key)
    private_keys: List[str] = []
    for key_record in keys_records:
        key = decoder.decrypt(data=key_record["private_key"], nonce=key_record["nonce"])
        hex = Web3.to_hex(int(key))
        private_keys.append(f"0x{hex[2:].zfill(64)}")  # pad missing leading zeros

    if not exists(output_dir):
        mkdir(output_dir)

    # check current keys
    current_keys = []
    for filename in glob.glob(os.path.join(output_dir, "*.yaml")):
        with open(os.path.join(os.getcwd(), filename), "r") as f:
            content = yaml.safe_load(f.read())
            current_keys.append(content.get("privateKey"))

    if is_lists_equal(current_keys, private_keys):
        click.secho(
            "Keys already synced to the last version.\n",
            bold=True,
            fg="green",
        )
        return

    # save key files
    for index, private_key in enumerate(private_keys):
        filename = f"key_{index}.yaml"
        with open(os.path.join(output_dir, filename), "w") as f:
            f.write(_generate_key_file(private_key))

    click.secho(
        f"Web3Signer now uses {len(private_keys)} private keys.\n",
        bold=True,
        fg="green",
    )


def _generate_key_file(private_key: str) -> str:
    item = {
        "type": "file-raw",
        "keyType": "BLS",
        "privateKey": private_key,
    }
    return yaml.dump(item)
