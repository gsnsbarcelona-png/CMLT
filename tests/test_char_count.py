from app.services.char_count import TWEET_CHAR_LIMIT, count_chars, within_limit


def test_ascii_text():
    assert count_chars("hola mundo") == len("hola mundo")


def test_url_counts_as_23_regardless_of_length():
    short = "mira https://x.co esto"
    long = "mira https://example.com/una/url/muy/larga/con/muchos/segmentos esto"
    assert count_chars(short) == len("mira  esto") + 23
    assert count_chars(long) == len("mira  esto") + 23


def test_multiple_urls():
    text = "https://a.com y tambien https://b.com/algo"
    without_urls = " y tambien "
    assert count_chars(text) == len(without_urls) + 23 * 2


def test_emoji_counts_as_single_code_point():
    assert count_chars("hola 😀") == len("hola ") + 1


def test_exact_boundary():
    text_280 = "a" * 280
    text_281 = "a" * 281
    assert count_chars(text_280) == TWEET_CHAR_LIMIT
    assert within_limit(text_280) is True
    assert count_chars(text_281) == TWEET_CHAR_LIMIT + 1
    assert within_limit(text_281) is False


def test_empty_string():
    assert count_chars("") == 0
    assert within_limit("") is True
