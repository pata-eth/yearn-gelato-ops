import pytest
from brownie import YearnGelatoOps, Contract, Wei, interface


# Snapshots the chain before each test and reverts after test completion.
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


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

    # gelato_proxy = "0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c"
    # yGO = YearnGelatoOps.deploy(lens.address, gelato_proxy, {"from": owner})

    yGO = YearnGelatoOps.deploy(lens.address, gelato.address, {"from": owner})

    # get some AETH donations to pay for jobs
    whale.transfer(yGO, amount)

    # gas price is set to zero in the fork
    assert yGO.balance() == amount

    # get USDC to test sweep function
    usdc.transfer(yGO, usdc_amount, {"from": usdc_whale})

    assert usdc.balanceOf(yGO) == usdc_amount

    yield yGO


# @pytest.fixture(scope="function")
# def yHarvestDeployed():
#     yield Contract("0x9AB353057CF41CfbA981a37e6C8F3942cc0147b6")


@pytest.fixture(scope="function")
def gelato():
    # yield Contract("0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c")
    yield interface.IGelatoOps("0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c")
    # yield interface.IGelatoOps("0xa5f9b728eceb9a1f6fcc89dcc2efd810ba4dec41")
    # yield Contract.from_explorer(
    #     address="0x340759c8346A1E6Ed92035FB8B6ec57cE1D82c2c",
    #     as_proxy_for="0xa5f9b728eceb9a1f6fcc89dcc2efd810ba4dec41"
    # )


# Optimism WETH AaveV3GenLender
@pytest.fixture(scope="function")
def strategy(yGO, sms):
    strategy = Contract(
        "0xf1a2DAB4C02563137ff1Ba34a8C9f92C2F8eeE49", owner=sms
    )
    # Make the yGO contract the strategy's keeper
    strategy.setKeeper(yGO.address)
    yield strategy


# Optimism USDC AaveV3GenLender
@pytest.fixture(scope="function")
def strategy_not_onboarded(sms):
    strategy = Contract(
        "0x20D27AC263A8B0f15D20614b0D63a4381997407c", owner=sms
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
    yield interface.ERC20("0x7f5c764cbc14f9669b88837ca1490cca17c31607")


@pytest.fixture(scope="module")
def native():
    yield "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"


# Define any accounts in this section
@pytest.fixture(scope="module")
def gov(accounts):
    yield accounts.at("0xF5d9D6133b698cE29567a90Ab35CfB874204B3A7", force=True)


@pytest.fixture(scope="module")
def sms(accounts):
    yield accounts.at("0xea3a15df68fCdBE44Fdb0DB675B2b3A14a148b26", force=True)


@pytest.fixture(scope="module")
def owner(accounts):
    yield accounts.at("0x2757AE02F65dB7Ce8CF2b2261c58f07a0170e58e", force=True)


@pytest.fixture(scope="module")
def whale(accounts):
    yield accounts.at("0xacD03D601e5bB1B275Bb94076fF46ED9D753435A", force=True)


@pytest.fixture(scope="module")
def usdc_whale(accounts):
    yield accounts.at("0xD6216fC19DB775Df9774a6E33526131dA7D19a2c", force=True)
