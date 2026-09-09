def test_chunk_text_basic(import_fresh):
    chunking = import_fresh("retrieval_service", "chunking")
    words = " ".join(f"w{i}" for i in range(1200))
    chunks = chunking.chunk_text(words, chunk_size=500, overlap=50)

    assert len(chunks) == 3
    # overlap: last 50 words of chunk 1 should reappear at the start of chunk 2
    assert chunks[0].split()[-1] == chunks[1].split()[49]


def test_chunk_text_empty_input_returns_no_chunks(import_fresh):
    chunking = import_fresh("retrieval_service", "chunking")
    assert chunking.chunk_text("", chunk_size=500, overlap=50) == []
    assert chunking.chunk_text("   ", chunk_size=500, overlap=50) == []


def test_chunk_text_shorter_than_chunk_size_returns_one_chunk(import_fresh):
    chunking = import_fresh("retrieval_service", "chunking")
    chunks = chunking.chunk_text("just a few words here", chunk_size=500, overlap=50)
    assert len(chunks) == 1


def test_chunk_text_zero_overlap_no_duplication(import_fresh):
    chunking = import_fresh("retrieval_service", "chunking")
    words = " ".join(f"w{i}" for i in range(30))
    chunks = chunking.chunk_text(words, chunk_size=10, overlap=0)
    assert len(chunks) == 3
    assert chunks[0].split()[-1] != chunks[1].split()[0]
