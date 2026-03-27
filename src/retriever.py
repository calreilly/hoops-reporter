import os
import glob
from dotenv import load_dotenv
import chromadb
import chromadb.utils.embedding_functions as embedding_functions
from rank_bm25 import BM25Okapi
import re
import uuid

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
        self.metadatas = []
        self.bm25 = None
        
        # Hydrate active corpus from Chroma if exists
        self._load_from_db()

    def _load_from_db(self):
        """Loads existing documents from Chroma into memory for BM25."""
        try:
            existing = self.collection.get()
            if existing and existing.get('documents'):
                self.documents = existing['documents']
                self.metadatas = existing.get('metadatas', [{} for _ in self.documents])
                self._train_bm25()
                print(f"[RAG] Hydrated {len(self.documents)} chunks from vector DB.")
            else:
                print("[RAG] Vector DB is empty.")
        except Exception as e:
            print(f"[RAG] Error loading from DB: {e}")

    def _train_bm25(self):
        if self.documents:
            tokenized_corpus = [self._tokenize(doc) for doc in self.documents]
            self.bm25 = BM25Okapi(tokenized_corpus)
        else:
            self.bm25 = None

    def _tokenize(self, text: str):
        # Basic lowercase alphanumeric tokenization
        return re.findall(r'\w+', text.lower())

    def ingest(self):
        print("Starting batch ingestion from data directory...")
        files = glob.glob(os.path.join(self.data_dir, "*.txt"))
        
        docs = []
        ids = []
        metas = []
        
        for i, filepath in enumerate(files):
            with open(filepath, 'r') as f:
                content = f.read()
            
            chunks = content.split('\n\n')
            for j, chunk in enumerate(chunks):
                if not chunk.strip(): continue
                doc_id = f"file_{i}_chunk_{j}_{uuid.uuid4().hex[:6]}"
                docs.append(chunk.strip())
                ids.append(doc_id)
                metas.append({"source": os.path.basename(filepath), "chunk": j})
                
        if docs:
            self.collection.upsert(
                documents=docs,
                metadatas=metas,
                ids=ids
            )
            # Rehydrate from DB
            self._load_from_db()
        else:
            print("No documents found to ingest.")

    def add_document(self, text: str, source_name: str):
        """Dynamic Knowledge Base Manager: Chunk and embed new text on the fly."""
        chunks = text.split('\n\n')
        docs = []
        ids = []
        metas = []
        
        for j, chunk in enumerate(chunks):
            if not chunk.strip(): continue
            doc_id = f"dynamic_{uuid.uuid4().hex[:8]}_chunk_{j}"
            docs.append(chunk.strip())
            ids.append(doc_id)
            metas.append({"source": source_name, "chunk": j})
            
        if docs:
            self.collection.upsert(
                documents=docs,
                metadatas=metas,
                ids=ids
            )
            print(f"[RAG] Ingested {len(docs)} new chunks from {source_name}")
            self._load_from_db() # sync in-memory lists
            return len(docs)
        return 0
        
    def get_all_documents(self):
        """Return distinct source names currently in the DB."""
        sources = set()
        for m in self.metadatas:
            if m and 'source' in m:
                sources.add(m['source'])
        return list(sources)

    def hybrid_search(self, query: str, top_k: int = 3):
        print(f"\nEvaluating query using Hybrid Search: '{query}'")
        
        if not self.documents:
            return []
            
        # 1. Vector Search
        vector_results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        
        vector_docs = vector_results['documents'][0] if vector_results['documents'] else []
        vector_metas = vector_results['metadatas'][0] if vector_results['metadatas'] else [{} for _ in vector_docs]
        
        # Build dicts for semantic
        v_results = [{"content": d, "metadata": m} for d, m in zip(vector_docs, vector_metas)]
        
        # 2. BM25 Search
        b_results = []
        if self.bm25:
            tokenized_query = self._tokenize(query)
            bm25_docs = self.bm25.get_top_n(tokenized_query, self.documents, n=top_k)
            # Find metadatas by matching text
            for doc in bm25_docs:
                try:
                    idx = self.documents.index(doc)
                    meta = self.metadatas[idx]
                except ValueError:
                    meta = {}
                b_results.append({"content": doc, "metadata": meta})
            
        # 3. Reciprocal Rank Fusion (Simple Set Union by content to deduplicate)
        combined = []
        seen = set()
        
        for v_res, b_res in zip(v_results + [None]*top_k, b_results + [None]*top_k):
            if v_res and v_res["content"] not in seen:
                combined.append(v_res)
                seen.add(v_res["content"])
            if b_res and b_res["content"] not in seen:
                combined.append(b_res)
                seen.add(b_res["content"])
                
        return combined[:top_k]

if __name__ == "__main__":
    retriever = HybridRetriever("src/data")
    retriever.ingest()
    
    print("\n--- Testing Retrieval ---")
    results = retriever.hybrid_search("Clingan rebounds vs Marquette")
    for idx, r in enumerate(results):
        print(f"RESULT {idx+1} (Source: {r['metadata'].get('source')}): {r['content'][:100]}...\n")
