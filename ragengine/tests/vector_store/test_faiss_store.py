import os
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from ragengine.vector_store.base import BaseVectorStore
from ragengine.vector_store.faiss_store import FaissVectorStoreHandler
from ragengine.models import Document
from ragengine.embedding.huggingface_local import LocalHuggingFaceEmbedding
from ragengine.config import MODEL_ID, INFERENCE_URL, INFERENCE_ACCESS_SECRET
from ragengine.config import PERSIST_DIR

@pytest.fixture(scope='session')
def init_embed_manager():
    return LocalHuggingFaceEmbedding(MODEL_ID)

@pytest.fixture
def vector_store_manager(init_embed_manager):
    with TemporaryDirectory() as temp_dir:
        print(f"Saving temporary test storage at: {temp_dir}")
        # Mock the persistence directory
        os.environ['PERSIST_DIR'] = temp_dir
        yield FaissVectorStoreHandler(init_embed_manager)

def test_index_documents(vector_store_manager):
    first_doc_text, second_doc_text = "First document", "Second document"
    documents = [
        Document(text=first_doc_text, metadata={"type": "text"}),
        Document(text=second_doc_text, metadata={"type": "text"})
    ]
    
    doc_ids = vector_store_manager.index_documents("test_index", documents)
    
    assert len(doc_ids) == 2
    assert set(doc_ids) == {BaseVectorStore.generate_doc_id(first_doc_text),
                            BaseVectorStore.generate_doc_id(second_doc_text)}

def test_index_documents_isolation(vector_store_manager):
    documents1 = [
        Document(text="First document in index1", metadata={"type": "text"}),
    ]
    documents2 = [
        Document(text="First document in index2", metadata={"type": "text"}),
    ]

    # Index documents in separate indices
    index_name_1, index_name_2 = "index1", "index2"
    vector_store_manager.index_documents(index_name_1, documents1)
    vector_store_manager.index_documents(index_name_2, documents2)

    assert vector_store_manager.list_all_indexed_documents() == {
        'index1': {"87117028123498eb7d757b1507aa3e840c63294f94c27cb5ec83c939dedb32fd":
                       {'hash': '1e64a170be48c45efeaa8667ab35919106da0489ec99a11d0029f2842db133aa',
                        'text': 'First document in index1'}},
        'index2': {"49b198c0e126a99e1975f17b564756c25b4ad691a57eda583e232fd9bee6de91":
                       {'hash': 'a222f875b83ce8b6eb72b3cae278b620de9bcc7c6b73222424d3ce979d1a463b',
                        'text': 'First document in index2'}}
    }

@patch('requests.post')
def test_query_documents(mock_post, vector_store_manager):
    # Define Mock Response for Custom Inference API
    mock_response = {
        "result": "This is the completion from the API"
    }

    mock_post.return_value.json.return_value = mock_response

    # Add documents to index
    documents = [
        Document(text="First document", metadata={"type": "text"}),
        Document(text="Second document", metadata={"type": "text"})
    ]
    vector_store_manager.index_documents("test_index", documents)

    params = {"temperature": 0.7}
    # Mock query and results
    query_result = vector_store_manager.query("test_index", "First", top_k=1, llm_params=params)

    assert query_result is not None
    assert query_result["response"] == "{'result': 'This is the completion from the API'}"
    assert query_result["source_nodes"][0]["text"] == "First document"
    assert query_result["source_nodes"][0]["score"] == pytest.approx(0.5795239210128784, rel=1e-6)

    mock_post.assert_called_once_with(
        INFERENCE_URL,
        # Auto-Generated by LlamaIndex
        json={"prompt": "Context information is below.\n---------------------\ntype: text\n\nFirst document\n---------------------\nGiven the context information and not prior knowledge, answer the query.\nQuery: First\nAnswer: ", "formatted": True, 'temperature': 0.7},
        headers={"Authorization": f"Bearer {INFERENCE_ACCESS_SECRET}"}
    )

def test_add_document(vector_store_manager):
    documents = [Document(text="Third document", metadata={"type": "text"})]
    vector_store_manager.index_documents("test_index", documents)

    # Add a document to the existing index
    new_document = [Document(text="Fourth document", metadata={"type": "text"})]
    vector_store_manager.index_documents("test_index", new_document)

    # Assert that the document exists
    assert vector_store_manager.document_exists("test_index",
                                                BaseVectorStore.generate_doc_id("Fourth document"))

def test_persist_index_1(vector_store_manager):
    """Test that the index store is persisted."""
    # Add a document and persist the index
    documents = [Document(text="Test document", metadata={"type": "text"})]
    vector_store_manager.index_documents("test_index", documents)
    vector_store_manager._persist("test_index")
    assert os.path.exists(PERSIST_DIR)

def test_persist_index_2(vector_store_manager):
    """Test that an index store is persisted."""
    # Add a document and persist the index
    documents = [Document(text="Test document", metadata={"type": "text"})]
    vector_store_manager.index_documents("test_index", documents)

    documents = [Document(text="Another Test document", metadata={"type": "text"})]
    vector_store_manager.index_documents("another_test_index", documents)

    vector_store_manager._persist_all()
    assert os.path.exists(PERSIST_DIR)
