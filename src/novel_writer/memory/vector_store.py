"""Vector Store - ChromaDB-based storage for chapter chunks and RAG retrieval."""

import re
from typing import Optional
from dataclasses import dataclass

import chromadb
from chromadb.config import Settings as ChromaSettings

from ..config import settings


@dataclass
class Document:
    """Retrieved document from vector store."""
    content: str
    chapter_id: int
    entities: list[str]
    summary: str
    distance: float


class VectorStore:
    """
    向量存储 - 用于存储章节切片和语义检索。
    
    基于 ChromaDB 实现，支持：
    - 章节内容的分块存储
    - 基于关键词/实体的语义搜索
    - 元数据过滤
    """
    
    def __init__(self, novel_id: str, persist_directory: Optional[str] = None):
        """
        Initialize vector store for a specific novel.
        
        Args:
            novel_id: Unique identifier for the novel
            persist_directory: Directory to persist the database
        """
        self.novel_id = novel_id
        
        if persist_directory:
            persist_path = persist_directory
        else:
            persist_path = str(settings.chroma_dir / novel_id)
        
        self.client = chromadb.PersistentClient(
            path=persist_path,
            settings=ChromaSettings(anonymized_telemetry=False)
        )
        
        self.collection = self.client.get_or_create_collection(
            name=f"novel_{novel_id}",
            metadata={"hnsw:space": "cosine"}
        )
    
    def add_chapter(
        self, 
        chapter_id: int, 
        content: str, 
        summary: str = "",
        entities: Optional[list[str]] = None,
        chunk_size: int = 500,
        overlap: int = 100
    ) -> int:
        """
        Add a chapter to the vector store, splitting into chunks.
        
        Args:
            chapter_id: Chapter number
            content: Full chapter content
            summary: Chapter summary
            entities: List of entities (characters, items, locations) in this chapter
            chunk_size: Size of each chunk in characters
            overlap: Overlap between chunks
            
        Returns:
            Number of chunks added
        """
        if entities is None:
            entities = []
        
        # Split content into chunks
        chunks = self._split_text(content, chunk_size, overlap)
        
        if not chunks:
            return 0
        
        # Prepare documents
        documents = []
        metadatas = []
        ids = []
        
        for i, chunk in enumerate(chunks):
            doc_id = f"ch{chapter_id}_chunk{i}"
            documents.append(chunk)
            metadatas.append({
                "chapter_id": chapter_id,
                "chunk_index": i,
                "entities": ",".join(entities),
                "summary": summary[:500] if summary else "",
            })
            ids.append(doc_id)
        
        # Upsert to collection
        self.collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        return len(chunks)
    
    def search(
        self, 
        query: str, 
        chapter_filter: Optional[int] = None,
        top_k: int = 5
    ) -> list[Document]:
        """
        Search for relevant chunks.
        
        Args:
            query: Search query
            chapter_filter: Optional filter to specific chapter
            top_k: Number of results to return
            
        Returns:
            List of relevant documents
        """
        where_filter = None
        if chapter_filter is not None:
            where_filter = {"chapter_id": chapter_filter}
        
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter
        )
        
        documents = []
        if results["documents"] and results["documents"][0]:
            for i, content in enumerate(results["documents"][0]):
                metadata = results["metadatas"][0][i] if results["metadatas"] else {}
                distance = results["distances"][0][i] if results["distances"] else 0.0
                
                documents.append(Document(
                    content=content,
                    chapter_id=metadata.get("chapter_id", 0),
                    entities=metadata.get("entities", "").split(",") if metadata.get("entities") else [],
                    summary=metadata.get("summary", ""),
                    distance=distance
                ))
        
        return documents
    
    def search_by_entities(
        self, 
        entities: list[str], 
        top_k: int = 5
    ) -> list[Document]:
        """
        Search for chunks containing specific entities.
        
        Args:
            entities: List of entity names to search for
            top_k: Number of results per entity
            
        Returns:
            List of relevant documents, deduplicated
        """
        all_docs = []
        seen_contents = set()
        
        for entity in entities:
            # Search using entity as query
            docs = self.search(entity, top_k=top_k)
            for doc in docs:
                # Deduplicate by content hash
                content_hash = hash(doc.content[:100])
                if content_hash not in seen_contents:
                    seen_contents.add(content_hash)
                    all_docs.append(doc)
        
        # Sort by distance (relevance)
        all_docs.sort(key=lambda x: x.distance)
        return all_docs[:top_k * 2]  # Return more for multiple entities
    
    def delete_chapter(self, chapter_id: int):
        """Delete all chunks for a specific chapter."""
        # Get all document IDs for this chapter
        results = self.collection.get(
            where={"chapter_id": chapter_id}
        )
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
    
    def _split_text(self, text: str, chunk_size: int, overlap: int) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries."""
        if not text:
            return []
        
        # Split by sentences
        sentences = re.split(r'([。！？\.\!\?]+)', text)
        
        # Recombine sentences with their punctuation
        combined = []
        for i in range(0, len(sentences) - 1, 2):
            combined.append(sentences[i] + (sentences[i + 1] if i + 1 < len(sentences) else ""))
        if len(sentences) % 2 == 1:
            combined.append(sentences[-1])
        
        # Build chunks
        chunks = []
        current_chunk = ""
        
        for sentence in combined:
            if len(current_chunk) + len(sentence) <= chunk_size:
                current_chunk += sentence
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                # Start new chunk with overlap from previous
                if overlap > 0 and chunks:
                    overlap_text = chunks[-1][-overlap:] if len(chunks[-1]) > overlap else chunks[-1]
                    current_chunk = overlap_text + sentence
                else:
                    current_chunk = sentence
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks
    
    def get_chapter_count(self) -> int:
        """Get the number of unique chapters stored."""
        results = self.collection.get()
        if not results["metadatas"]:
            return 0
        
        chapter_ids = set()
        for metadata in results["metadatas"]:
            if "chapter_id" in metadata:
                chapter_ids.add(metadata["chapter_id"])
        
        return len(chapter_ids)
