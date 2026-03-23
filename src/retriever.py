import os
import glob
from dotenv import load_dotenv
import chromadb
import chromadb.utils.embedding_functions as embedding_functions
from rank_bm25 import BM25Okapi
import re

load_dotenv()

class HybridRetriever:
    def __init__(self, data_dir: str, persist_dir: str = "./chroma_db"):
        self.data_dir = data_dir
        self.chroma_client = chromadb.PersistentClient(path=persist_dir)
        
        # Use OpenAI Embeddings if key exists, otherwise default Chroma minilm
        if os.getenv("OPENAI_API_KEY"):
            print("Using OpenAI Embeddings")
            self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=os.getenv("OPENAI_API_KEY"),
                model_name="text-embedding-3-small"
            )
        else:
            print("Using Default Minilm Embeddings")
            self.embedding_fn = embedding_functions.DefaultEmbeddingFunction()

        self.collection = self.chroma_client.get_or_create_collection(
            name="hoops_news",
            embedding_function=self.embedding_fn
        )
        self.documents = []
        self.bm25 = None

    def ingest(self):
        print("Starting ingestion...")
        files = glob.glob(os.path.join(self.data_dir, "*.txt"))
        
        docs = []
        ids = []
        metadatas = []
        
        for i, filepath in enumerate(files):
            with open(filepath, 'r') as f:
                content = f.read()
            
            # Simple chunking by double newline (paragraphs)
            chunks = content.split('\n\n')
            for j, chunk in enumerate(chunks):
                if not chunk.strip(): continue
                doc_id = f"doc_{i}_chunk_{j}"
                docs.append(chunk.strip())
                ids.append(doc_id)
                metadatas.append({"source": os.path.basename(filepath), "chunk": j})
                
        if docs:
            # Upsert into Chroma (Vector DB)
            self.collection.upsert(
                documents=docs,
                metadatas=metadatas,
                ids=ids
            )
            # Train BM25 (Keyword Search)
            tokenized_corpus = [self._tokenize(doc) for doc in docs]
            self.bm25 = BM25Okapi(tokenized_corpus)
            self.documents = docs
            print(f"Ingested {len(docs)} chunks.")
        else:
            print("No documents found to ingest.")
            
    def _tokenize(self, text: str):
        # Basic lowercase alphanumeric tokenization
        return re.findall(r'\w+', text.lower())

    def hybrid_search(self, query: str, top_k: int = 3):
        print(f"\nEvaluating query using Hybrid Search: '{query}'")
        
        # 1. Vector Search
        vector_results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        vector_docs = vector_results['documents'][0] if vector_results['documents'] else []
        
        # 2. BM25 Search
        if not self.bm25 and self.documents:
            # Reload BM25 if already ingested
            tokenized_corpus = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_corpus)
            
        bm25_docs = []
        if self.bm25:
            tokenized_query = self._tokenize(query)
            bm25_docs = self.bm25.get_top_n(tokenized_query, self.documents, n=top_k)
            
        # 3. Reciprocal Rank Fusion (Simple Set Union)
        combined = []
        seen = set()
        
        for v_doc, b_doc in zip(vector_docs + [None]*top_k, bm25_docs + [None]*top_k):
            if v_doc and v_doc not in seen:
                combined.append(v_doc)
                seen.add(v_doc)
            if b_doc and b_doc not in seen:
                combined.append(b_doc)
                seen.add(b_doc)
                
        return combined[:top_k]

if __name__ == "__main__":
    retriever = HybridRetriever("src/data")
    retriever.ingest()
    
    print("\n--- Testing Retrieval ---")
    results = retriever.hybrid_search("Clingan rebounds vs Marquette")
    for idx, r in enumerate(results):
        print(f"RESULT {idx+1}: {r}\n")
