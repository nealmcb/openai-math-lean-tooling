import Lean
import Export.Parse

/-- Time Lean's own kernel on an export file the way Comparator's `runBuiltinKernel` does (parse the export, then `Environment.replay` into a fresh
kernel environment, with the Quot constants removed from the map). Prints the parse time and the replay time in milliseconds and whether the kernel accepted.
Local tool for the kernel timing study (tools/kernel_replay_time.lean is a copy). Usage: replaytime EXPORT_FILE -/
def main (args : List String) : IO UInt32 := do
  let some path := args.head? | do IO.eprintln "usage: replaytime EXPORT_FILE"; return 2
  let h ← IO.FS.Handle.mk (System.FilePath.mk path) IO.FS.Mode.read
  let t0 ← IO.monoMsNow
  let solution ← Export.parseStream (IO.FS.Stream.ofHandle h)
  let t1 ← IO.monoMsNow
  IO.println s!"parsed in {t1 - t0} ms"
  let env ← Lean.mkEmptyEnvironment
  let quotTargets := [`Quot.mk, `Quot.lift, `Quot.ind]
  let kernelConstMap := quotTargets.foldl (init := solution.constMap) (·.erase ·)
  try
    let _ ← env.toKernelEnv.replay kernelConstMap
    let t2 ← IO.monoMsNow
    IO.println s!"Lean kernel accepts; replay {t2 - t1} ms"
    return 0
  catch e =>
    let t2 ← IO.monoMsNow
    IO.println s!"Lean kernel rejects after {t2 - t1} ms: {e.toString}"
    return 1
