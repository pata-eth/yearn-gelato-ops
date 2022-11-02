from brownie import Contract, interface, accounts, chain


def main():
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
        want_i = Contract(strat_i.want())
        vault = Contract(strat_i.vault())
        lastReport = vault.strategies(strat_i)[5]

        print(
            f"{want_i.symbol()+' '+strat_i.name()} ({i}) has "
            f"{strat_i.estimatedTotalAssets()//10**want_i.decimals():_} "
            "in assets."
        )
        print(
            f"       minReportDelay is {strat_i.minReportDelay() // (60 * 60)} "
            f"hours and maxReportDelay is "
            f"{strat_i.maxReportDelay()// (60 * 60)} hours."
        )
        print(f"       keeper is {strat_i.keeper()}")
        print(
            f"       last report was {(chain.time() - lastReport) // 3_600} "
            "hours ago"
        )
        should_harvest = strat_i.harvestTrigger(harvet_cost)
        print(f"       harvest trigger is {should_harvest}", end="")
        if should_harvest:
            print("; harvesting...\n")
            strat_i.harvest()
        # fast-forward 12 hours
        chain.sleep(12 * 3_600)
        should_harvest = strat_i.harvestTrigger(harvet_cost)
        print(f"       harvest trigger is now {should_harvest}\n")
