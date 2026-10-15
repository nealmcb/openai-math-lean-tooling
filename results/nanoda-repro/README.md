# Minimal reproduction: nanoda aborts with a stack overflow on a valid export

The export `sizeFactor_positive.export` (7.7 MB; `.xz`, `.gz` and `.zst` copies here) is the Lean export of one theorem,
`OAI.DFVSGames.Foundations.PCP.RoundTables.sizeFactor_positive`, and everything it depends on, from the openai/math library. Lean's own kernel accepts it
(it is in a library that compiles, and Comparator's full check of the configuration it belongs to, DirectedFeedback, is accepted by Lean's kernel). nanoda aborts.

Reproduce:

    git clone https://github.com/ammkrn/nanoda_lib && cd nanoda_lib && git checkout 3a2407216ee84a75f9e1aead6803d0578be06ae7
    cargo build --release
    xz -dk sizeFactor_positive.export.xz
    target/release/nanoda_bin nanoda-config.json      # config as Comparator writes it, with num_threads 4

Expected: a verdict. Observed, in about one second:

    thread 'thread_0' has overflowed its stack
    fatal runtime error: stack overflow, aborting        (SIGABRT, exit 134)

The checker threads are created with `.stack_size(crate::STACK_SIZE)`, a constant of 16 MiB (src/lib.rs). Raising it to 1 GiB (rebuilt nanoda) does not help the larger
export `sizeFactor_positive` + `build_size_le` (30.5 MB): it overflows after 76 s instead of 1 s.

How the export was made (Lean 4.34.1, openai/math commit fd4aeeb2ee4fc729c18d98444fed42fd0529eeeb, lean4export 076e8e57707e813375e8f9da8bf989799ace9680, project built):

    lake env lean4export OAI.Computability.DirectedFeedback.Main -- OAI.DFVSGames.Foundations.PCP.RoundTables.sizeFactor_positive \
      Quot Quot.mk Quot.lift Quot.ind Nat.add Nat.sub Nat.mul Nat.pow Nat.gcd Nat.div Nat.mod Nat.beq Nat.ble Nat.land Nat.lor Nat.xor Nat.shiftLeft \
      Nat.shiftRight String.ofList Char.ofNat List eagerReduce Nat String String.mk Char optParam autoParam semiOutParam outParam propext Quot.sound Classical.choice
