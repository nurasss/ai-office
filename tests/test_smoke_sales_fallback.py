from scripts.smoke_first_task import build_offline_fallback, extract_monthly_sales


SALES_REPORT_TEXT = """
Январь 450 120 54 000 Февраль 410 115 47 150 Март 520 125 65 000
Апрель 480 130 62 400 Май 600 140 84 000 Июнь 750 145 108 750
Июль 820 150 123 000 Август 790 140 110 600 Сентябрь 580 135 78 300
Октябрь 540 130 70 200 Ноябрь 670 145 97 150 Декабрь 1 100 160 176 000
"""


def test_extract_monthly_sales_from_pdf_text():
    monthly_sales = extract_monthly_sales(SALES_REPORT_TEXT)

    assert monthly_sales["Январь"]["revenue"] == 54000
    assert monthly_sales["Декабрь"]["units"] == 1100
    assert monthly_sales["Декабрь"]["revenue"] == 176000


def test_build_offline_fallback_calculates_quarters():
    result = build_offline_fallback(
        agent_id="data_analyst",
        task="Проанализируй продажи по кварталам и выручку за первый квартал",
        rag_text=SALES_REPORT_TEXT,
    )

    assert "Выручка за первый квартал: `$166 150`" in result
    assert "Q4: $343 350" in result
    assert "Больше всего выручки вышло в Q4" in result


def test_build_offline_fallback_skips_partial_report():
    result = build_offline_fallback(
        agent_id="data_analyst",
        task="Проанализируй продажи по кварталам",
        rag_text="Январь 450 120 54 000 Февраль 410 115 47 150",
    )

    assert result == ""


def test_build_offline_fallback_answers_best_month_and_reason():
    result = build_offline_fallback(
        agent_id="data_analyst",
        task=(
            "Проанализируй годовой отчет о продажах, напиши какой самый "
            "прибыльный квартал и какой самый прибыльный месяц, и почему"
        ),
        rag_text=SALES_REPORT_TEXT + "Пик продаж: всплеск в декабре из-за праздничного сезона.",
    )

    assert "прибыльность' трактуется как максимальная выручка" in result
    assert "Больше всего выручки вышло в Q4" in result
    assert "Самый прибыльный месяц по выручке: Декабрь `$176 000`" in result
    assert "праздничный сезон" in result
    assert "1 100 единиц" in result
    assert "$160" in result
