theory Example
  imports Main "HOL-Library.Multiset"
begin

(* This comment mentions lemma not_a_real_lemma to test comment stripping. *)

definition square :: "nat \<Rightarrow> nat" where
  "square n = n * n"

lemma square_nonneg: "square n \<ge> 0"
  by (simp add: square_def)

theorem add_commute: "a + b = b + (a::nat)"
  by simp

datatype 'a tree = Leaf | Node "'a tree" 'a "'a tree"

fun mirror :: "'a tree \<Rightarrow> 'a tree" where
  "mirror Leaf = Leaf"
| "mirror (Node l x r) = Node (mirror r) x (mirror l)"

lemma "rev (rev xs) = xs"
  by simp

end
