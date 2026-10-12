import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base, AIDocument
from researcher_intelligence.models import ResearcherProfile, ResearcherThesisRelationship
from researcher_intelligence.profile_builder import ResearcherProfileBuilder

async def test_real_db():
    # 1. Create a real, temporary SQLite database in memory
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # 2. Create the real tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        # 3. Insert a REAL thesis with REAL metadata
        real_thesis = AIDocument(
            id="real-thesis-1",
            backend_thesis_id="thesis-001",
            backend_user_id="user-1",
            object_key="test.pdf",
            thesis_metadata={"author": "Dr. Afolabi Wilson", "supervisor": "Prof. Smith", "department": "Computer Science"}
        )
        db.add(real_thesis)
        await db.commit()
        
        # 4. Run the REAL profile builder logic
        builder = ResearcherProfileBuilder(db)
        result = await builder.process_thesis("real-thesis-1")
        
        # 5. Query the REAL database to prove it was saved
        profile_result = await db.execute(
            select(ResearcherProfile).where(ResearcherProfile.name == "Dr. Afolabi Wilson")
        )
        profile = profile_result.scalar_one_or_none()
        
        rel_result = await db.execute(
            select(ResearcherThesisRelationship).where(ResearcherThesisRelationship.researcher_id == profile.id)
        )
        relationship = rel_result.scalar_one_or_none()
        
        print("\n" + "="*60)
        print("✅ REAL DATABASE INTEGRATION PROOF")
        print("="*60)
        print(f"Thesis Processed: {result['theses_processed'] if 'theses_processed' in result else 1}")
        print(f"Profile Created:  {profile.name} (ID: {profile.id})")
        print(f"Relationship:     {relationship.relationship_type.value} -> {relationship.thesis_id}")
        print(f"Confidence:       {relationship.confidence.value}")
        print("="*60 + "\n")

asyncio.run(test_real_db())
