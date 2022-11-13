from brownie import YearnGelatoOps, accounts, network, Wei, interface, convert
from enum import Enum
import click
import json


class jobTypes(int, Enum):
    MONITOR = 0
    HARVEST = 1
    TEND = 2


def main():
    print(f"You are using the '{network.show_active()}' network")
    dev = accounts.load(
        click.prompt("Account", type=click.Choice(accounts.load()))
    )
    print(f"You are using: 'dev' [{dev.address}]")

    lens = interface.IYearnLens("0xD3A93C794ee2798D8f7906493Cd3c2A835aa0074")

    gelato = interface.IGelatoOps("0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c")

    yGO = YearnGelatoOps.deploy(lens, gelato, {"from": dev})

    # Create verification file we can manually upload to optiscan
    with open("./contracts/YearnGelatoOps.json", "w") as outfile:
        json.dump(
            YearnGelatoOps.get_verification_info()["standard_json_input"],
            outfile,
            ensure_ascii=False,
            indent=4,
        )

    # Fund the yGO contract
    amount = Wei("0.3 ether")
    dev.transfer(yGO, amount)

    assert yGO.balance() == amount

    # Create Strategy Monitoring job
    tx = yGO.createJob(jobTypes.MONITOR, yGO.address)

    tx.info()

    # Ensure that the strategy monitor does not detect any strategy
    canExec, execData = yGO.checkNewStrategies()

    assert not canExec
    assert convert.to_string(execData) == "No new strategies to automate"
