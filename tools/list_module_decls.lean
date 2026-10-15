/-
list_module_decls: print the non-internal declarations that each of the given modules itself defines, one `module<TAB>name` line per declaration.

Purpose: tools/uncovered_check.py exports and nanoda-checks the declarations of modules that no Comparator solution imports; lean4export wants constant names, so this lists
them (importing the given modules, then keeping the constants whose defining module is one of them). Run through `lake env` in src/lean so the OAI .olean files are on LEAN_PATH:
  lake env lean --run tools/list_module_decls.lean OAI.A.B OAI.C.D ...
-/
import Lean
open Lean

def main (args : List String) : IO Unit := do
  initSearchPath (← findSysroot)
  let env ← importModules (args.toArray.map fun m => { module := Syntax.decodeNameLit ("`" ++ m) |>.get! }) {}
  let wanted : Std.HashSet Name := args.foldl (fun s m => s.insert (Syntax.decodeNameLit ("`" ++ m)).get!) {}
  let out ← IO.getStdout
  for (c, _) in env.constants.toList do
    if c.isInternal then continue
    if let some i := env.getModuleIdxFor? c then
      let m := env.header.moduleNames[i.toNat]!
      if wanted.contains m then out.putStrLn s!"{m}\t{c}"
