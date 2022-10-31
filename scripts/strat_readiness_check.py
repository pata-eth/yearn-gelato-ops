from brownie import Contract, interface, accounts, chain

lens = interface.IYearnLens("0xD3A93C794ee2798D8f7906493Cd3c2A835aa0074")

strats = lens.assetsStrategiesAddresses()

# seafood yearn watch strats
# strats = [
#     "0xAfccb36CAEEB089611c1085BCA783214A1a47691",
#     "0x20D27AC263A8B0f15D20614b0D63a4381997407c",
#     "0x390978489417b984CeFDfde102F78e67F64B1091",
#     "0xb448dae03108dDd66374bAabCaA6d95E7dfEfD1D",
#     "0x18128146C33d821A484F3D43fF2b986BEBd0c8F3",
#     "0xD1c8dC4e30194e3a9DC65c65a150eaF5Ab037008",
#     ]

opti_sms = accounts.at(
    "0xea3a15df68fCdBE44Fdb0DB675B2b3A14a148b26", force=True
)

# https://optimistic.etherscan.io/tx/0xe8882152cd3bf2f8492742e6340881b2531b38d16eafc9a0cba7f1c7ebce1115
harvet_cost = 225249291820000  # wei

for i in strats:
    strat_i = Contract(i, owner=opti_sms)
    vault = Contract(strat_i.vault())
    lastReport = vault.strategies(strat_i)[5]
    # struct StrategyParams:
    # performanceFee: uint256  # Strategist's fee (basis points)
    # activation: uint256  # Activation block.timestamp
    # debtRatio: uint256  # Maximum borrow amount (in BPS of total assets)
    # minDebtPerHarvest: uint256  # Lower limit on the increase of debt since
    #   last harvest
    # maxDebtPerHarvest: uint256  # Upper limit on the increase of debt since
    #   last harvest
    # lastReport: uint256  # block.timestamp of the last time a report occured
    # totalDebt: uint256  # Total outstanding debt that Strategy has
    # totalGain: uint256  # Total returns that Strategy has realized for Vault
    # totalLoss: uint256  # Total losses that Strategy has realized for Vault

    print(
        f"Strategy {i} has {strat_i.estimatedTotalAssets()/10**18:_} "
        "in assets.\n"
    )
    print(
        f"        minReportDelay is {strat_i.minReportDelay() // (60 * 60)} "
        f"hours and maxReportDelay is {strat_i.maxReportDelay()// (60 * 60)}"
        " hours.\n"
    )
    print(f"        keeper is {strat_i.keeper()}\n")
    should_harvest = strat_i.harvestTrigger(harvet_cost)
    print(f"        harvest trigger is {should_harvest}", end="")
    if should_harvest:
        print("; harvesting...\n")
        tx = strat_i.harvest()
    # fast-forward 12 hours
    chain.sleep(12 * 60 * 60)
    should_harvest = strat_i.harvestTrigger(harvet_cost)
    print(f"        harvest trigger is now {should_harvest}\n")
