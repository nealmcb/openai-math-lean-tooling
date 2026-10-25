-- Theorems for tools/nanoda_let_tests.py. A theorem `foo_bad` (proved by `sorry`) only donates its
-- false statement: the script gives `foo`'s proof that statement and expects nanoda to reject it.

-- the value is substituted into the arithmetic
theorem let_pos1 : (let x : Nat := 2; x + 1) = 3 := rfl
theorem let_pos1_bad : (let x : Nat := 2; x + 1) = 4 := sorry

-- two sibling lets with the same name and type, different values
theorem let_sib : (let x : Nat := 1; x) = 1 ∧ (let x : Nat := 2; x) = 2 := ⟨rfl, rfl⟩
theorem let_sib_bad : (let x : Nat := 1; x) = 1 ∧ (let x : Nat := 2; x) = 1 := sorry

-- an inner let shadows an outer one with the same name and type
theorem let_shadow : (let x : Nat := 1; let x : Nat := 2; x) = 2 := rfl
theorem let_shadow_bad : (let x : Nat := 1; let x : Nat := 2; x) = 1 := sorry

-- a let-bound function, unfolded when applied to an argument
theorem let_func : (let f : Nat → Nat := fun y => y + 1; f 2) = 3 := rfl
theorem let_func_bad : (let f : Nat → Nat := fun y => y + 1; f 2) = 4 := sorry

-- the value mentions a variable bound outside the let
theorem let_under_binder : ∀ z : Nat, (let x : Nat := z + 1; x) = z + 1 := fun _ => rfl
theorem let_under_binder_bad : ∀ z : Nat, (let x : Nat := z + 1; x) = z + 2 := sorry

-- a type that depends on the let-bound variable
theorem let_fin : let n : Nat := 2; ∀ i : Fin n, i.val < n := by intro n i; exact i.isLt
theorem let_fin_bad : let n : Nat := 2; ∀ i : Fin n, i.val < 1 := sorry

-- a let inside a type
theorem let_in_type : (let n : Nat := 2; Fin n) = Fin 2 := rfl
theorem let_in_type_bad : (let n : Nat := 2; Fin n) = Fin 3 := sorry

-- two declarations with lets of the same name and type: nothing may carry over between them
theorem let_xd1 : (let x : Nat := 1; x) = 1 := rfl
theorem let_xd2 : (let x : Nat := 2; x) = 2 := rfl
theorem let_xd2_bad : (let x : Nat := 2; x) = 1 := sorry

-- Proofs whose type checking needs a let-bound variable's value (checking the argument `rfl`
-- against `decide (...) = true` evaluates the variable). The script builds variants in which a
-- value is replaced, by finding the let whose value is the literal 55 or 66 (unique in this file)
-- and giving it the value of `let x : Nat := 1` above. A checker that confused two lets with the
-- same name and type would accept those variants.
theorem let_sibv : True ∧ True :=
  ⟨let n : Nat := 5; (fun (_ : decide (4 < n) = true) => trivial) rfl,
   let n : Nat := 55; (fun (_ : decide (4 < n) = true) => trivial) rfl⟩
theorem let_shadowv : True :=
  let n : Nat := 5; let n : Nat := 66; (fun (_ : decide (4 < n) = true) => trivial) rfl
-- the same need for a value, through an applied let-bound function and under a binder
theorem let_funcv : True :=
  let f : Nat → Nat := fun y => y + 3; (fun (_ : decide (f 2 = 5) = true) => trivial) rfl
theorem let_binderv : ∀ z : Nat, True :=
  fun z => let x : Nat := z + 7; (fun (_ : x = z + 7) => trivial) rfl

-- The script also builds a variant in which the inner let (`vtyx`, value 77, unique in this file)
-- gets the Bool value of the outer one; nothing uses the value, so only the check of the value
-- against the annotation can reject it. lean4export shares nodes regardless of binder names, so
-- the inner let is found by position.
theorem let_vty : (let vtyb : Bool := true; let vtyx : Nat := 77; 5) = 5 := rfl

-- well-typed only
theorem let_dep : let n : Nat := 3; let m : Nat := n + n; m = 6 := rfl
theorem let_ty : let α : Type := Nat; ((fun (a : α) => a) (5 : Nat)) = 5 := rfl
theorem let_big : let d : Nat := 2 ^ 70; d * 2 = 2 ^ 71 := rfl
