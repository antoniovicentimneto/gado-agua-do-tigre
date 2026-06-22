"""Fixtures de teste: banco SQLite em memória com alguns animais semeados."""
from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Animal, AnimalLote, Lote, Pesagem, StatusAnimal


@pytest.fixture
def db():
    """Sessão de banco isolada (em memória) para cada teste."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine)
    s = Sessao()

    # Semeia: lote LOTEA com 2 animais (com pesagens) + lote LOTEB com 1.
    lote_a = Lote(nome="LOTEA")
    lote_b = Lote(nome="LOTEB")
    s.add_all([lote_a, lote_b])
    s.flush()

    def cria(brinco, tipo, lote, pesos):
        a = Animal(brinco=brinco, tipo=tipo, status=StatusAnimal.ATIVO)
        s.add(a)
        s.flush()
        s.add(AnimalLote(animal_id=a.id, lote_id=lote.id, data_inicio=date(2026, 1, 1)))
        for d, p in pesos:
            s.add(Pesagem(animal_id=a.id, data=d, peso=p))
        return a

    cria("101", "Novilha", lote_a, [(date(2026, 1, 1), 300), (date(2026, 5, 1), 400)])
    cria("102", "Boi", lote_a, [(date(2026, 1, 1), 320)])
    cria("201", "Vaca", lote_b, [(date(2026, 1, 1), 450)])
    s.commit()

    yield s
    s.close()
