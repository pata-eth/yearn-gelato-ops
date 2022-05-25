from brownie import YearnHarvester, accounts, network, Contract, web3
from eth_utils import is_checksum_address
import click


def get_address(msg: str, default: str = None) -> str:
    val = click.prompt(msg, default=default)

    # Keep asking user for click.prompt until it passes
    while True:

        if is_checksum_address(val):
            return val
        elif addr := web3.ens.address(val):
            click.echo(f"Found ENS '{val}' [{addr}]")
            return addr

        click.echo(
            f"I'm sorry, but '{val}' is not a checksummed address or valid ENS record"
        )
        # NOTE: Only display default once
        val = click.prompt(msg)


def main():
    print(f"You are using the '{network.show_active()}' network")
    owner = accounts.load(click.prompt("Account", type=click.Choice(accounts.load())))
    print(f"You are using: 'owner' [{owner.address}]")

    publish_source = click.confirm("Verify source on etherscan?")
    if input("Deploy Strategy? y/[N]: ").lower() != "y":
        return

    yHarvest = YearnHarvester.deploy({"from": owner}, publish_source=publish_source)

    strategy = Contract("0xA9a904B5567b5AFfb6bB334bea2f90F700EB221a")

    strategy.setKeeper(yHarvest.address, {"from": owner})
