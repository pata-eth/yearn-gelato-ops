from enum import Enum
import pytest
from brownie import YearnGelatoOps, Contract, Wei, interface


class jobTypes(int, Enum):
    MONITOR = 0
    HARVEST = 1
    TEND = 2


# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture(scope="session")
def job_types():
    yield jobTypes


@pytest.fixture(scope="module")
def lens():
    yield interface.IYearnLens("0xD3A93C794ee2798D8f7906493Cd3c2A835aa0074")


# `baseFee` is provided to harvestTrigger() in the checker function
# as the actual fee is not available there
@pytest.fixture(scope="module")
def baseFee():
    yield Wei("0.0000000001 ether")


# `gelatoFee` is the fee provided by Gelato executors to the exec() method
# We use it to simulate actual fees
@pytest.fixture(scope="module")
def gelatoFee():
    yield Wei("0.001 ether")


@pytest.fixture(scope="function")
def yGO(
    lens,
    gelato,
    owner,
    whale,
    amount,
    usdc_amount,
    usdc_whale,
    usdc,
):

    yGO = YearnGelatoOps.deploy(lens.address, gelato.address, common_report_trigger.address, {"from": owner})

    # get some AETH donations to pay for jobs
    whale.transfer(yGO, amount)

    # gas price is set to zero in the fork
    assert yGO.balance() == amount

    # get USDC to test sweep function
    usdc.transfer(yGO, usdc_amount, {"from": usdc_whale})

    assert usdc.balanceOf(yGO) == usdc_amount

    yield yGO


# @pytest.fixture(scope="function")
# def yGO():
#     yield Contract("0xA9a904B5567b5AFfb6bB334bea2f90F700EB221a")


@pytest.fixture(scope="function")
def gelato():
    yield interface.IGelatoOps("0x527a819db1eb0e34426297b03bae11F2f8B3A19E")

@pytest.fixture(scope="module")
def common_report_trigger():
    yield interface.ICommonReportTrigger("0x4D25b3aed34eC1222846F6C87e2ac4A73f4ab6b6")


# Polygon yearn-v3 WETH AaveV3Lender
@pytest.fixture(scope="function")
def strategy(yGO, sms):
    strategy = Contract(
        "0x5f76526390d9cd9944d65C605C5006480FA1bFcB", owner=sms
    )
    # Make the yGO contract the strategy's keeper
    strategy.setKeeper(yGO.address)
    yield strategy


# Polygon yearn-v3 USDC CompoundV3Lender
@pytest.fixture(scope="function")
def strategy_not_onboarded(sms):
    strategy = Contract(
        "0xF32C48793CAe27880D18Ee4697fAB6D08748228E", owner=sms
    )
    yield strategy


@pytest.fixture(scope="module")
def amount():
    yield Wei("50 ether")


@pytest.fixture(scope="module")
def usdc_amount(usdc):
    yield 10_000 * 10 ** usdc.decimals()


@pytest.fixture(scope="module")
def usdc():
    yield interface.ERC20("0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174")


@pytest.fixture(scope="module")
def native():
    yield "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


# Define any accounts in this section
@pytest.fixture(scope="module")
def gov(accounts):
    yield accounts.at("0xC4ad0000E223E398DC329235e6C497Db5470B626", force=True) #yearn governance on polygon


@pytest.fixture(scope="module")
def sms(accounts):
    yield accounts.at("0x16388000546eDed4D476bd2A4A374B5a16125Bc1", force=True)


@pytest.fixture(scope="module")
def owner(accounts):
    yield accounts.at("0x33333333D5eFb92f19a5F94a43456b3cec2797AE", force=True)


@pytest.fixture(scope="module")
def whale(accounts):
    yield accounts.at("0xe7804c37c13166fF0b37F5aE0BB07A3aEbb6e245", force=True)


@pytest.fixture(scope="module")
def usdc_whale(accounts):
    yield accounts.at("0xf977814e90da44bfa03b6295a0616a897441acec", force=True)
