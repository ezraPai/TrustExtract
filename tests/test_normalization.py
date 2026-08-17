from pipeline.normalization import normalize_for_field


def test_normalizes_layout_only_differences_for_text_fields():
    assert normalize_for_field("company", "TF Value-Mart Sdn. Bhd") == "TFVALUEMARTSDNBHD"
    assert normalize_for_field("address", "No. 1, Jalan Angsa") == "NO1JALANANGSA"


def test_normalizes_dates_and_money():
    assert normalize_for_field("date", "19/05/18") == "2018-05-19"
    assert normalize_for_field("date", "2018-05-19") == "2018-05-19"
    assert normalize_for_field("date", "04 JUN 2018") == "2018-06-04"
    assert normalize_for_field("date", "(06/12/2016)") == "2016-12-06"
    assert normalize_for_field("date", "12/28/2017") == "2017-12-28"
    assert normalize_for_field("date", "20180304") == "2018-03-04"
    assert normalize_for_field("date", "OCT 3, 2016") == "2016-10-03"
    assert normalize_for_field("total", "RM 1,234.50") == "1234.50"
    assert normalize_for_field("total", "20,50") == "20.50"
