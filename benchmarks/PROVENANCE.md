# Benchmark provenance

Every public specification used in this project is pinned to an exact
commit and redistributed under its upstream licence.  `PROVENANCE.json`
holds the SHA-256 of each file; verify with
`python benchmarks/fetch_public_specs.py --verify`.

## Sources

| Repository | Commit | Files fetched |
|---|---|---|
| `ongardie/raft.tla` | `6ecbdbcf1bcd` | 1 |
| `tlaplus/Examples` | `ca168055339d` | 562 |

## Candidate models

| Model | Directory | Family |
|---|---|---|
| `raft` | `.` | consensus |
| `MC` | `specifications/CarTalkPuzzle/CarTalkPuzzle.toolbox/Model_1` | puzzle |
| `Chameneos` | `specifications/Chameneos` | synchronisation |
| `MCCheckpointCoordination` | `specifications/CheckpointCoordination` | replication |
| `CigaretteSmokers` | `specifications/CigaretteSmokers` | synchronisation |
| `CoffeeCan100Beans` | `specifications/CoffeeCan` | puzzle |
| `DieHard` | `specifications/DieHard` | puzzle |
| `DiningPhilosophers` | `specifications/DiningPhilosophers` | mutual-exclusion |
| `MCDisruptor_SPMC` | `specifications/Disruptor` | concurrent-data-structure |
| `Einstein` | `specifications/EinsteinRiddle` | puzzle |
| `MCReplicatedLog` | `specifications/FiniteMonotonic` | replication |
| `MCFlashWithMutex` | `specifications/FlashProtocol` | cache-coherence |
| `GameOfLife` | `specifications/GameOfLife` | puzzle |
| `MCGermanCMPWithMutex` | `specifications/GermanProtocol` | cache-coherence |
| `MCGermanControl` | `specifications/GermanProtocol` | cache-coherence |
| `MCGermanData` | `specifications/GermanProtocol` | cache-coherence |
| `Huang` | `specifications/Huang` | distributed-algorithm |
| `MCKVSSafetySmall` | `specifications/KeyValueStore` | replication |
| `MCFindHighest` | `specifications/LearnProofs` | sequential-algorithm |
| `MCLeastCircularSubstringSmall` | `specifications/LeastCircularSubstring` | sequential-algorithm |
| `MCBinarySearch` | `specifications/LoopInvariance` | sequential-algorithm |
| `MCMajority` | `specifications/Majority` | distributed-algorithm |
| `MissionariesAndCannibals` | `specifications/MissionariesAndCannibals` | puzzle |
| `CatEvenBoxes` | `specifications/Moving_Cat_Puzzle` | puzzle |
| `ElevatorSafetySmall` | `specifications/MultiCarElevator` | concurrent-data-structure |
| `MultiPaxos_MC` | `specifications/MultiPaxos-SMR` | consensus |
| `MultiPaxos_MC_small` | `specifications/MultiPaxos-SMR` | consensus |
| `MC` | `specifications/N-Queens/Queens.toolbox/FourQueens` | puzzle |
| `MCNanoSmall` | `specifications/NanoBlockchain` | replication |
| `MCConsensus` | `specifications/Paxos` | consensus |
| `MCPaxos` | `specifications/Paxos` | consensus |
| `MCVoting` | `specifications/Paxos` | consensus |
| `MCConsensus` | `specifications/PaxosHowToWinATuringAward` | consensus |
| `MCPaxosSmall` | `specifications/PaxosHowToWinATuringAward` | consensus |
| `MCPaxosTiny` | `specifications/PaxosHowToWinATuringAward` | consensus |
| `MCVoting` | `specifications/PaxosHowToWinATuringAward` | consensus |
| `Prisoners` | `specifications/Prisoners` | synchronisation |
| `MC` | `specifications/ReadersWriters` | mutual-exclusion |
| `FastPaxos` | `specifications/SimplifiedFastPaxos` | consensus |
| `Paxos` | `specifications/SimplifiedFastPaxos` | consensus |
| `SlidingPuzzles` | `specifications/SlidingPuzzles` | puzzle |
| `SlushSmall` | `specifications/SlushProtocol` | consensus |
| `SpanTreeTest4Nodes` | `specifications/SpanningTree` | distributed-algorithm |
| `abstract` | `specifications/SpecificationRefinement` | refinement |
| `bad` | `specifications/SpecificationRefinement` | refinement |
| `good` | `specifications/SpecificationRefinement` | refinement |
| `MCInnerSequential` | `specifications/SpecifyingSystems/AdvancedExamples` | protocol |
| `MCInnerSerial` | `specifications/SpecifyingSystems/AdvancedExamples` | protocol |
| `AsynchInterface` | `specifications/SpecifyingSystems/AsynchronousInterface` | protocol |
| `Channel` | `specifications/SpecifyingSystems/AsynchronousInterface` | protocol |
| `MCInternalMemory` | `specifications/SpecifyingSystems/CachingMemory` | cache-coherence |
| `MCWriteThroughCache` | `specifications/SpecifyingSystems/CachingMemory` | cache-coherence |
| `MCInnerFIFO` | `specifications/SpecifyingSystems/FIFO` | protocol |
| `HourClock` | `specifications/SpecifyingSystems/HourClock` | protocol |
| `HourClock2` | `specifications/SpecifyingSystems/HourClock` | protocol |
| `LiveHourClock` | `specifications/SpecifyingSystems/Liveness` | protocol |
| `MCLiveWriteThroughCache` | `specifications/SpecifyingSystems/Liveness` | protocol |
| `ABCorrectness` | `specifications/SpecifyingSystems/TLC` | protocol |
| `MCAlternatingBit` | `specifications/SpecifyingSystems/TLC` | protocol |
| `StaleShrink` | `specifications/StaleViewShrink` | replication |
| `Stones` | `specifications/Stones` | puzzle |
| `Simple` | `specifications/TeachingConcurrency` | mutual-exclusion |
| `SimpleRegular` | `specifications/TeachingConcurrency` | mutual-exclusion |
| `TransitiveClosure` | `specifications/TransitiveClosure` | sequential-algorithm |
| `MCTwoPhase` | `specifications/TwoPhase` | transaction-commit |
| `MCYoYoPruning` | `specifications/YoYo` | distributed-algorithm |
| `aba_asyn_byz` | `specifications/aba-asyn-byz` | distributed-algorithm |
| `ACP_SB_TLC` | `specifications/acp` | protocol |
| `AllocatorImplementation` | `specifications/allocator` | allocation |
| `AllocatorRefinement` | `specifications/allocator` | allocation |
| `SchedulingAllocator` | `specifications/allocator` | allocation |
| `SimpleAllocator` | `specifications/allocator` | allocation |
| `Barrier` | `specifications/barriers` | synchronisation |
| `Barriers` | `specifications/barriers` | synchronisation |
| `bcastFolklore` | `specifications/bcastFolklore` | distributed-algorithm |
| `bosco` | `specifications/bosco` | distributed-algorithm |
| `BufferedRandomAccessFile` | `specifications/braf` | data-structure |
| `MCbtree` | `specifications/btree` | data-structure |
| `VoucherTransfer` | `specifications/byihive` | business-process |
| `Consensus` | `specifications/byzpaxos` | consensus |
| `c1cs` | `specifications/c1cs` | distributed-algorithm |
| `cf1s_folklore` | `specifications/cf1s-folklore` | distributed-algorithm |
| `MCChangRoberts` | `specifications/chang_roberts` | ring-token |
| `TLCSailfish1` | `specifications/dag-consensus` | consensus |
| `EnvironmentController` | `specifications/detector_chan96` | distributed-algorithm |
| `MC` | `specifications/dijkstra-mutex/DijkstraMutex.toolbox/Safety-4-processors` | mutual-exclusion |
| `MC_HDiskSynod` | `specifications/diskpaxos` | consensus |
| `MCEcho` | `specifications/echo` | ring-token |
| `TokenRing` | `specifications/ewd426` | ring-token |
| `MCEWD687a` | `specifications/ewd687a` | ring-token |
| `EWD840` | `specifications/ewd840` | termination-detection |
| `SyncTerminationDetection` | `specifications/ewd840` | termination-detection |
| `EWD998` | `specifications/ewd998` | termination-detection |
| `EWD998Small` | `specifications/ewd998` | termination-detection |
| `clean` | `specifications/glowingRaccoon` | distributed-algorithm |
| `MCLamportMutex` | `specifications/lamport_mutex` | mutual-exclusion |
| `Lock` | `specifications/locks_auxiliary_vars` | auxiliary-variables |
| `LockHS` | `specifications/locks_auxiliary_vars` | auxiliary-variables |
| `Peterson` | `specifications/locks_auxiliary_vars` | auxiliary-variables |
| `nbacc_ray97` | `specifications/nbacc_ray97` | distributed-algorithm |
| `nbacg_guer01` | `specifications/nbacg_guer01` | distributed-algorithm |
| `MC_spanning` | `specifications/spanning` | distributed-algorithm |
| `MC_sums_even` | `specifications/sums_even` | sequential-algorithm |
| `MCtcp` | `specifications/tcp` | protocol |
| `Hanoi_anim` | `specifications/tower_of_hanoi` | puzzle |
| `2PCwithBTM` | `specifications/transaction_commit` | transaction-commit |
| `PaxosCommit` | `specifications/transaction_commit` | transaction-commit |
| `TCommit` | `specifications/transaction_commit` | transaction-commit |
| `TwoPhase` | `specifications/transaction_commit` | transaction-commit |
