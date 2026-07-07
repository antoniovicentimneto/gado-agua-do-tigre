"""Schemas Pydantic (validação de entrada/saída da API)."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict

from .models import PapelUsuario, StatusAnimal, TipoSessao


class AnimalBase(BaseModel):
    brinco: str
    tipo: str | None = None
    raca: str | None = None
    cor: str | None = None
    vendedor: str | None = None
    nascimento: date | None = None
    capado: bool = False
    status: StatusAnimal = StatusAnimal.ATIVO
    observacao: str | None = None


class AnimalCriar(AnimalBase):
    pass


class AnimalAtualizar(BaseModel):
    brinco: str | None = None
    tipo: str | None = None
    raca: str | None = None
    cor: str | None = None
    vendedor: str | None = None
    nascimento: date | None = None
    capado: bool | None = None
    status: StatusAnimal | None = None
    observacao: str | None = None


class AnimalResumo(AnimalBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lote_atual: str | None = None
    ultimo_peso: float | None = None
    data_ultimo: date | None = None
    gmd: float | None = None
    ugmd: float | None = None


class PesagemBase(BaseModel):
    data: date
    peso: float


class PesagemCriar(PesagemBase):
    pass


class PesagemSaida(PesagemBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class PesagemRapida(BaseModel):
    """Registro rápido no curral: identifica o animal pelo brinco."""
    brinco: str
    data: date
    peso: float
    animal_id: int | None = None  # escolha quando há brincos repetidos


class DenticaoCriar(BaseModel):
    data: date
    dentes: int


class ScoreCriar(BaseModel):
    data: date
    valor: float


class LoteSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str


class OpcaoSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str


class OpcaoCriar(BaseModel):
    nome: str


class VendaCalculo(BaseModel):
    peso: float
    rendimento: float
    preco_arroba: float


class VendaCriar(VendaCalculo):
    data: date | None = None


class GmdPeriodoConsulta(BaseModel):
    inicio: date | None = None
    fim: date | None = None


# ---------------------------------------------------------------- Sessão de pesagem

class SessaoCriar(BaseModel):
    tipo: TipoSessao = TipoSessao.MANEJO
    data: date | None = None  # padrão: hoje
    lotes_origem: list[str] = []
    separar_lotes: bool = False
    sublotes: list[str] = []
    preco_kg: float | None = None
    preco_arroba: float | None = None
    vendedor: str | None = None


class SubloteCriar(BaseModel):
    nome: str


class PesarDados(BaseModel):
    brinco: str
    peso: float
    destino_lote: str | None = None
    observacao: str | None = None
    forcar: bool = False
    criar_animal: bool = False   # cadastro rápido quando o brinco não existe
    tipo: str | None = None      # tipo do animal no cadastro rápido
    animal_id: int | None = None  # desambiguação quando há brincos repetidos
    novo_tipo: str | None = None  # editar a classificação do animal na hora
    nova_raca: str | None = None  # editar a raça do animal na hora
    dentes: int | None = None     # registrar a dentição com a data da pesagem


class PesarSemBrinco(BaseModel):
    peso: float
    destino_lote: str | None = None
    observacao: str | None = None
    tipo: str | None = None


class VincularBrinco(BaseModel):
    animal_temp_id: int      # animal provisório (sem brinco / brinco novo) criado na sessão
    animal_faltante_id: int  # animal antigo que perdeu o brinco (herda o histórico)
    novo_brinco: str | None = None  # brinco novo a aplicar no animal antigo (opcional)


class VincularAvulso(BaseModel):
    animal_destino_id: int  # animal já existente que vai herdar o histórico
    novo_brinco: str | None = None  # brinco a aplicar no animal destino (opcional)


class CompletarVendaMorto(BaseModel):
    rendimento: float | None = None
    peso_carcaca: float | None = None
    preco_arroba: float | None = None


# ---------------------------------------------------------------- Lotes (gestão)

class LoteRenomear(BaseModel):
    nome: str


class LoteMover(BaseModel):
    animal_ids: list[int]
    destino: str  # nome do lote destino (cria se não existir)


class LoteJuntar(BaseModel):
    origem_id: int
    destino: str  # nome do lote destino


# ---------------------------------------------------------------- Usuários / login

class SetupDono(BaseModel):
    nome: str
    usuario: str
    senha: str


class Login(BaseModel):
    usuario: str
    senha: str


class UsuarioCriar(BaseModel):
    nome: str
    usuario: str
    senha: str
    papel: PapelUsuario = PapelUsuario.PEAO


class UsuarioSaida(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nome: str
    usuario: str
    papel: PapelUsuario


class PesagemEditar(BaseModel):
    peso: float | None = None
    destino_lote: str | None = None
    observacao: str | None = None
