from lecturelens_agent.study.atomic import AtomicAssessment, atomic_claims
from lecturelens_agent.study.freeze_certification import certify_assessments


def certify(answer, source, rejected=()):
    checks = [
        AtomicAssessment(
            **claim,
            supported=claim["id"] not in rejected,
            model_supported=claim["id"] not in rejected,
            evidence_ids=["own"] if claim["id"] not in rejected else [],
        )
        for claim in atomic_claims(answer)
    ]
    return certify_assessments(checks, {"own": source})


def test_possible_count_cannot_certify_exact_count_but_preserves_operands():
    source = "Each step potentially makes two comparisons with the left and right neighbours."
    exact = certify("The step makes two comparisons with the left and right neighbours.", source)
    assert not exact[0].supported
    assert "freeze_count_modality" in exact[0].strengthening_guards
    bounded = certify("The step makes at most two comparisons with the left and right neighbours.", source)
    assert bounded[0].supported
    hypothetical = certify("For example, two comparisons.", source)
    assert hypothetical[0].supported


def test_comparison_and_half_size_do_not_certify_a_choice_rule():
    source = "Compare the candidate with its neighbours. Recurse on a half-sized input."
    checks = certify(
        "If the signal is high, choose the left side and continue. The input size halves.", source
    )
    assert not checks[1].supported and "freeze_choice_relation" in checks[1].strengthening_guards
    assert not checks[2].supported and "freeze_dependent_scope" in checks[2].strengthening_guards
    assert checks[-1].supported
    explicit = certify(
        "If the signal is high, choose the left side and continue.",
        "If the signal is high, choose the left side and continue.",
    )
    assert all(check.supported for check in explicit)


def test_rejected_condition_keeps_its_consequent_editable_but_not_next_operation():
    answer = "If the signal is high, then continue recursively, each recursive step halves the input."
    checks = certify(answer, "Each recursive step halves the input.", rejected={"a1"})
    assert not checks[1].supported
    assert "freeze_dependent_scope" in checks[1].strengthening_guards
    assert checks[2].supported


def test_local_or_possible_source_does_not_certify_universal_claim():
    checks = certify("All items are updated.", "Some items are updated.")
    assert not checks[0].supported
    assert "freeze_global_scope" in checks[0].strengthening_guards


def test_unstated_conditional_comparator_does_not_protect_its_result():
    checks = certify(
        "If the candidate is at least as large as both neighbours, then return it.",
        "Compare the candidate with its neighbours.",
    )
    assert not checks[0].supported and "freeze_condition_predicate" in checks[0].strengthening_guards
    assert not checks[1].supported and "freeze_dependent_scope" in checks[1].strengthening_guards
