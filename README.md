# Exploring Gelato at Yearn Finance
## Summary
I explored Gelato's functionality via a new smart contract called Yearn Harvest that automates harvest jobs. Key points:

- yHarvest is deployed in Fantom and jobs are paid in FTM from the contract's balance after a succesful execution;
- It automatically creates a harvest job for active strategies that have yHarvest assigned as the keeper;
- A simulation of all active strategies with assets > 0 through yHarvest (25 out of 70) resulted in 11 succesful harvests. Reverted transactions were mainly due to healthcheck issues. Gelato does not execute jobs that revert in a simulation;
- Tested [the contract in production]([0x9AB353057CF41CfbA981a37e6C8F3942cc0147b6](https://ftmscan.com/address/0x9ab353057cf41cfba981a37e6c8f3942cc0147b6)) with the [Curve Tricrypto strategy](https://ftmscan.com/address/0xA9a904B5567b5AFfb6bB334bea2f90F700EB221a). The strategy monitoring job that listens for new strategies in Yearn Lens triggered and picked up tricrypto almost immediately, creating a harvest job for the strategy that also triggered without delay. 

Gelato is a fast-growing protocol that promises to tackle many of the pain points that other keeper networks have had, including MEV protection and the coordination of keepers with economic incentives that avoid winner-takes-all conditions. These benefits have helped Gelato lure important players in defi, including most recently MakerDAO. Let's see what the fuzz is all about.
 Please continue reading [here...](https://hackmd.io/@pata/H11Rmo9w9)