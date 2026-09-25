# app/database.py
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, JSON, ForeignKey, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DATABASE_PATH = DATA_DIR / "interncheck.db"

engine = create_engine(
    f"sqlite:///{DATABASE_PATH}",
    echo=False,  # Установить True для логирования SQL-запросов
    future=True
)

Base = declarative_base()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



class UserAnswer(Base):
    """Ответ пользователя на конкретный вопрос."""
    __tablename__ = "user_answers"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    question_id = Column(String, index=True)
    question_text = Column(Text)
    selected_option_id = Column(String)
    selected_option_text = Column(Text)
    is_correct = Column(Integer)  # 0 или 1
    correct_option_id = Column(String)
    skill_id = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_user_question', 'user_id', 'question_id'),
        Index('idx_user_skill', 'user_id', 'skill_id'),
        Index('idx_timestamp', 'timestamp'),
    )


class TestSession(Base):
    """Активная сессия теста (для продолжения прерванного теста)."""
    __tablename__ = "test_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, index=True)  # Один активный тест на пользователя
    test_id = Column(String)
    test_name = Column(String)
    current_question = Column(Integer, default=0)
    total_questions = Column(Integer)
    started_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # JSON поля для хранения данных теста
    test_data = Column(JSON)  # Полная структура теста
    skills = Column(JSON)     # Список навыков
    answers = Column(JSON)    # Список ответов (question_id, option_id, is_correct)


class TestResult(Base):
    """Результаты завершенного теста."""
    __tablename__ = "test_results"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    test_id = Column(String, index=True)
    test_name = Column(String)
    total_score = Column(Integer)
    overall_percent = Column(Float)
    skill_scores = Column(JSON)  # {"python": 85, "sql": 70}
    is_ready = Column(Integer)  # 0 или 1
    questions_count = Column(Integer)
    timestamp = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(engine)



def get_db():
    """Контекстный менеджер для работы с сессией."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



def save_test_session(user_id: int, session_data: dict) -> None:
    """Сохраняет или обновляет активную сессию теста."""
    db = SessionLocal()
    try:
        existing = db.query(TestSession).filter(TestSession.user_id == user_id).first()
        
        if existing:
            # Обновляем существующую сессию
            existing.test_id = session_data.get("test_data", {}).get("id", "")
            existing.test_name = session_data.get("test_data", {}).get("name", "")
            existing.current_question = session_data.get("current_question", 0)
            existing.total_questions = len(session_data.get("test_data", {}).get("questions", []))
            existing.test_data = session_data.get("test_data", {})
            existing.skills = session_data.get("skills", [])
            existing.answers = session_data.get("answers", [])
            existing.last_updated = datetime.utcnow()
        else:
            # Создаем новую сессию
            new_session = TestSession(
                user_id=user_id,
                test_id=session_data.get("test_data", {}).get("id", ""),
                test_name=session_data.get("test_data", {}).get("name", ""),
                current_question=session_data.get("current_question", 0),
                total_questions=len(session_data.get("test_data", {}).get("questions", [])),
                test_data=session_data.get("test_data", {}),
                skills=session_data.get("skills", []),
                answers=session_data.get("answers", [])
            )
            db.add(new_session)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Ошибка при сохранении сессии: {e}")
    finally:
        db.close()


def get_test_session(user_id: int) -> dict:
    """Получает активную сессию теста пользователя."""
    db = SessionLocal()
    try:
        session = db.query(TestSession).filter(TestSession.user_id == user_id).first()
        
        if session:
            return {
                "test_data": session.test_data,
                "skills": session.skills,
                "current_question": session.current_question,
                "answers": session.answers or []
            }
        return None
    finally:
        db.close()


def clear_test_session(user_id: int) -> None:
    """Удаляет активную сессию теста."""
    db = SessionLocal()
    try:
        session = db.query(TestSession).filter(TestSession.user_id == user_id).first()
        if session:
            db.delete(session)
            db.commit()
    except Exception as e:
        db.rollback()
        print(f"Ошибка при удалении сессии: {e}")
    finally:
        db.close()



def save_user_answer(user_id: int, question_id: str, answer_data: dict) -> None:
    """Сохраняет ответ пользователя на вопрос."""
    db = SessionLocal()
    try:
        existing = db.query(UserAnswer).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.question_id == question_id
        ).first()
        
        if existing:
            existing.selected_option_id = answer_data.get("selected_option_id", "")
            existing.selected_option_text = answer_data.get("selected_option_text", "")
            existing.is_correct = 1 if answer_data.get("is_correct") else 0
            existing.correct_option_id = answer_data.get("correct_option_id", "")
            existing.skill_id = answer_data.get("skill_id", "")
            existing.timestamp = datetime.utcnow()
        else:
            # Создаем новую запись
            new_answer = UserAnswer(
                user_id=user_id,
                question_id=question_id,
                question_text=answer_data.get("question_text", ""),
                selected_option_id=answer_data.get("selected_option_id", ""),
                selected_option_text=answer_data.get("selected_option_text", ""),
                is_correct=1 if answer_data.get("is_correct") else 0,
                correct_option_id=answer_data.get("correct_option_id", ""),
                skill_id=answer_data.get("skill_id", "")
            )
            db.add(new_answer)
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Ошибка при сохранении ответа: {e}")
    finally:
        db.close()


def get_user_answers(user_id: int) -> list:
    """Получает все ответы пользователя."""
    db = SessionLocal()
    try:
        answers = db.query(UserAnswer).filter(UserAnswer.user_id == user_id).all()
        
        result = []
        for ans in answers:
            result.append({
                "question_id": ans.question_id,
                "question_text": ans.question_text,
                "selected_option_id": ans.selected_option_id,
                "selected_option_text": ans.selected_option_text,
                "is_correct": bool(ans.is_correct),
                "correct_option_id": ans.correct_option_id,
                "skill_id": ans.skill_id,
                "timestamp": ans.timestamp.isoformat() if ans.timestamp else None
            })
        
        return result
    finally:
        db.close()



def save_test_result(user_id: int, test_result: dict) -> None:
    """Сохраняет результаты завершенного теста."""
    db = SessionLocal()
    try:
        result = TestResult(
            user_id=user_id,
            test_id=test_result.get("test_id", ""),
            test_name=test_result.get("test_name", ""),
            total_score=test_result.get("total_score", 0),
            overall_percent=test_result.get("overall_percent", 0.0),
            skill_scores=test_result.get("skill_scores", {}),
            is_ready=1 if test_result.get("is_ready") else 0,
            questions_count=test_result.get("questions_count", 0)
        )
        db.add(result)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Ошибка при сохранении результата теста: {e}")
    finally:
        db.close()


def get_test_history(user_id: int) -> list:
    """Получает историю тестов пользователя."""
    db = SessionLocal()
    try:
        results = db.query(TestResult).filter(
            TestResult.user_id == user_id
        ).order_by(TestResult.timestamp.desc()).all()
        
        history = []
        for res in results:
            history.append({
                "test_id": res.test_id,
                "test_name": res.test_name,
                "total_score": res.total_score,
                "overall_percent": res.overall_percent,
                "skill_scores": res.skill_scores,
                "is_ready": bool(res.is_ready),
                "questions_count": res.questions_count,
                "timestamp": res.timestamp.isoformat() if res.timestamp else None
            })
        
        return history
    finally:
        db.close()


def get_user_stats(user_id: int) -> dict:
    """Получает статистику по пользователю."""
    db = SessionLocal()
    try:
        # Количество пройденных тестов
        total_tests = db.query(TestResult).filter(TestResult.user_id == user_id).count()
        
        # Общее количество ответов
        total_answers = db.query(UserAnswer).filter(UserAnswer.user_id == user_id).count()
        
        # Правильные ответы
        correct_answers = db.query(UserAnswer).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.is_correct == 1
        ).count()
        
        # Статистика по навыкам
        from sqlalchemy import func
        skill_stats = db.query(
            UserAnswer.skill_id,
            func.count(UserAnswer.id).label('total'),
            func.sum(UserAnswer.is_correct).label('correct')
        ).filter(
            UserAnswer.user_id == user_id,
            UserAnswer.skill_id.isnot(None)
        ).group_by(UserAnswer.skill_id).all()
        
        skills_summary = {}
        for skill_id, total, correct in skill_stats:
            if total > 0:
                skills_summary[skill_id] = {
                    "correct": int(correct or 0),
                    "total": total,
                    "percent": round((int(correct or 0) / total) * 100)
                }
        
        return {
            "total_tests": total_tests,
            "total_answers": total_answers,
            "correct_answers": correct_answers,
            "accuracy": round((correct_answers / total_answers * 100), 1) if total_answers > 0 else 0,
            "skills": skills_summary
        }
    finally:
        db.close()