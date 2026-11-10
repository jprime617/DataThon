"""Testes de propriedade da Junta_Relacional (`src/enriquecimento.py`).

Cobre a normalização das chaves municipais das duas bases (CAGED e IBGE) para
o identificador comum de 6 dígitos numéricos, ou a rejeição (``None``) de
códigos malformados (R3.1, R3.2, R3.6).
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.enriquecimento import chave_municipal_caged, chave_municipal_ibge


# Estratégia de entradas heterogêneas que cobre o espaço de códigos municipais:
# inteiros (positivos e negativos), floats (incluindo não inteiros e NaN),
# textos de dígitos de qualquer comprimento, texto arbitrário, None e booleanos.
_entradas_chave = st.one_of(
    st.integers(min_value=-10, max_value=99_999_999),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(alphabet="0123456789", min_size=0, max_size=10),
    st.text(max_size=12),
    st.none(),
    st.booleans(),
)


# Feature: datathon-caged-sc-pipeline, Property 9: Normalização da chave municipal
# produz 6 dígitos ou rejeita — para qualquer entrada, a normalização ou produz
# exatamente 6 dígitos numéricos ou retorna None (rejeitando o código malformado);
# no CAGED, códigos de até 6 dígitos são preenchidos à esquerda com zeros; no IBGE,
# códigos válidos de 7 dígitos produzem os seus 6 primeiros dígitos.
# Validates: Requirements 3.1, 3.2
@given(codigo=_entradas_chave)
@settings(max_examples=100)
def test_chave_municipal_produz_6_digitos_ou_rejeita(codigo):
    chave_caged = chave_municipal_caged(codigo)
    chave_ibge = chave_municipal_ibge(codigo)

    # Invariante central (ambas as bases): ou None, ou exatamente 6 dígitos.
    for chave in (chave_caged, chave_ibge):
        if chave is not None:
            assert isinstance(chave, str)
            assert len(chave) == 6
            assert chave.isdigit()

    # Especialização CAGED: um resultado não nulo é o código com zero-padding
    # à esquerda para 6 posições (equivalente a interpretar como inteiro).
    if chave_caged is not None:
        assert int(chave_caged) == int(chave_caged.lstrip("0") or "0")

    # Especialização IBGE: um resultado não nulo são os 6 primeiros dígitos de
    # um código de exatamente 7 dígitos numéricos.
    if chave_ibge is not None:
        assert chave_ibge == _texto_digitos(codigo)[:6]
        assert len(_texto_digitos(codigo)) == 7


# Feature: datathon-caged-sc-pipeline, Property 9: Normalização da chave municipal
# produz 6 dígitos ou rejeita — verificação direcionada sobre códigos de dígitos
# bem-formados, confirmando o zero-padding do CAGED e o corte do verificador IBGE.
# Validates: Requirements 3.1, 3.2
@given(digitos=st.integers(min_value=0, max_value=999_999))
@settings(max_examples=100)
def test_caged_preenche_ate_6_digitos_e_ibge_rejeita_comprimento_errado(digitos):
    texto = str(digitos)

    # CAGED: qualquer código de até 6 dígitos vira exatamente 6, com zero-padding.
    chave_caged = chave_municipal_caged(texto)
    assert chave_caged is not None
    assert chave_caged == texto.zfill(6)

    # IBGE: um código de ≤6 dígitos não tem os 7 exigidos → rejeitado.
    assert chave_municipal_ibge(texto) is None

    # IBGE: anexar um 7º dígito torna-o válido e produz os 6 primeiros dígitos.
    for verificador in "0123456789":
        codigo7 = texto.zfill(6) + verificador
        assert chave_municipal_ibge(codigo7) == codigo7[:6]


def _texto_digitos(codigo: object) -> str:
    """Representação textual em dígitos de um código bem-formado (auxiliar do teste).

    Espelha a normalização textual do módulo apenas o suficiente para validar a
    especialização do IBGE; retorna string vazia para entradas não numéricas,
    que nunca satisfazem a pré-condição onde é usada.
    """
    if isinstance(codigo, bool) or codigo is None:
        return ""
    if isinstance(codigo, int):
        return str(codigo) if codigo >= 0 else ""
    if isinstance(codigo, float):
        if codigo != codigo or codigo in (float("inf"), float("-inf")):
            return ""
        return str(int(codigo)) if codigo.is_integer() and codigo >= 0 else ""
    texto = str(codigo).strip()
    if texto.endswith(".0") and texto[:-2].isdigit():
        texto = texto[:-2]
    return texto if texto.isdigit() else ""


# ---------------------------------------------------------------------------
# Testes de propriedade do left join (`juntar`) — tarefa 5.4
# ---------------------------------------------------------------------------

import pandas as pd

from src.enriquecimento import juntar


# Código municipal CAGED bem-formado: 1 a 6 dígitos (normaliza para 6 via zfill).
_codigo_caged_valido = st.integers(min_value=0, max_value=999_999).map(str)

# Código municipal CAGED malformado: rejeitado por `chave_municipal_caged`
# (não numérico, vazio, ou com mais de 6 dígitos).
_codigo_caged_malformado = st.one_of(
    st.text(alphabet="abcxyz-/ ", min_size=1, max_size=5),
    st.just(""),
    st.integers(min_value=1_000_000, max_value=99_999_999).map(str),
)

# Código IBGE bem-formado: exatamente 7 dígitos (normaliza para os 6 primeiros).
_codigo_ibge_valido = st.integers(min_value=1_000_000, max_value=9_999_999).map(str)

# Código IBGE malformado: rejeitado por `chave_municipal_ibge`
# (comprimento != 7 ou não numérico).
_codigo_ibge_malformado = st.one_of(
    st.text(alphabet="abcxyz-/ ", min_size=1, max_size=6),
    st.just(""),
    st.integers(min_value=0, max_value=999_999).map(str),
    st.integers(min_value=10_000_000, max_value=99_999_999).map(str),
)


def _df_caged(codigos: list[str]) -> pd.DataFrame:
    """Monta um CAGED mínimo com a coluna de código municipal e um payload."""
    return pd.DataFrame(
        {
            "município": codigos,
            "saldomovimentação": list(range(len(codigos))),
        }
    )


def _df_municipios(codigos: list[str]) -> pd.DataFrame:
    """Monta uma Base_de_Municipios mínima com o código IBGE e um indicador."""
    return pd.DataFrame(
        {
            "Código": codigos,
            "populacao": [1000 + i for i in range(len(codigos))],
        }
    )


# Feature: datathon-caged-sc-pipeline, Property 10: Left join preserva todo o CAGED válido
# — para qualquer CAGED e Base_de_Municipios, o resultado da junção contém exatamente
# um registro para cada linha do CAGED cuja chave é válida (left join preservador),
# e `total_caged` é igual a essa quantidade; linhas com chave malformada não aparecem.
# Validates: Requirements 3.3
@given(
    codigos_caged=st.lists(
        st.one_of(_codigo_caged_valido, _codigo_caged_malformado),
        min_size=0,
        max_size=40,
    ),
    codigos_mun=st.lists(_codigo_ibge_valido, min_size=0, max_size=20, unique=True),
)
@settings(max_examples=100)
def test_left_join_preserva_todo_o_caged_valido(codigos_caged, codigos_mun):
    df_caged = _df_caged(codigos_caged)
    df_mun = _df_municipios(codigos_mun)

    resultado = juntar(df_caged, df_mun)

    # Quantidade esperada de registros CAGED com chave válida.
    chaves_validas = [c for c in codigos_caged if chave_municipal_caged(c) is not None]
    assert resultado.total_caged_valido == len(chaves_validas)
    # `total_caged` é o total LIDO, antes de excluir chaves malformadas (R3.4).
    assert resultado.total_caged == len(codigos_caged)
    assert len(resultado.df) == len(chaves_validas)

    # O multiconjunto de chaves preservadas é exatamente o das linhas válidas do
    # CAGED (nenhuma perdida, nenhuma duplicada) — municípios são únicos, logo o
    # left join não multiplica linhas.
    esperadas = sorted(
        chave_municipal_caged(c) for c in chaves_validas
    )
    obtidas = sorted(resultado.df["chave_municipal"].tolist())
    assert obtidas == esperadas

    # O payload original de cada linha válida é preservado (nenhuma linha some).
    saldos_validos = sorted(
        s for c, s in zip(codigos_caged, range(len(codigos_caged)))
        if chave_municipal_caged(c) is not None
    )
    assert sorted(resultado.df["saldomovimentação"].tolist()) == saldos_validos


# Feature: datathon-caged-sc-pipeline, Property 11: Contagem de não correspondência e
# alerta de limiar são corretos — `sem_correspondencia` conta exatamente as linhas
# válidas do CAGED sem município correspondente; o alerta é emitido se e somente se
# essa proporção excede 1% do total, e nesse caso as contagens por código batem.
# Validates: Requirements 3.4, 3.5
@given(
    codigos_caged=st.lists(_codigo_caged_valido, min_size=0, max_size=60),
    codigos_mun=st.lists(_codigo_ibge_valido, min_size=0, max_size=20, unique=True),
)
@settings(max_examples=100)
def test_contagem_sem_correspondencia_e_alerta_de_limiar(codigos_caged, codigos_mun):
    df_caged = _df_caged(codigos_caged)
    df_mun = _df_municipios(codigos_mun)

    resultado = juntar(df_caged, df_mun)

    # Conjunto de chaves municipais presentes na base (6 dígitos).
    chaves_mun = {chave_municipal_ibge(c) for c in codigos_mun}

    # Contagem esperada de não correspondência: chaves CAGED fora da base.
    chaves_caged = [chave_municipal_caged(c) for c in codigos_caged]
    chaves_caged = [c for c in chaves_caged if c is not None]
    nao_corresp = [c for c in chaves_caged if c not in chaves_mun]

    assert resultado.total_caged == len(chaves_caged)
    assert resultado.sem_correspondencia == len(nao_corresp)

    # Alerta sse proporção > 1% do total.
    if resultado.total_caged > 0:
        proporcao = len(nao_corresp) / resultado.total_caged
        assert resultado.alerta == (proporcao > 0.01)
    else:
        assert resultado.alerta is False

    if resultado.alerta:
        # Contagens por código batem exatamente com os códigos não correspondidos.
        esperado: dict[str, int] = {}
        for c in nao_corresp:
            esperado[c] = esperado.get(c, 0) + 1
        assert resultado.codigos_nao_correspondidos == esperado
        # A soma das contagens por código iguala o total sem correspondência.
        assert sum(resultado.codigos_nao_correspondidos.values()) == len(nao_corresp)
    else:
        # Sem alerta, não se listam códigos (R3.5 só exige a lista acima do limiar).
        assert resultado.codigos_nao_correspondidos == {}


# Feature: datathon-caged-sc-pipeline, Property 12: Registros com chave malformada são
# excluídos e contados por base — para qualquer mistura de códigos bem-formados e
# malformados em cada base, a junção exclui os registros malformados e reporta a
# contagem de excluídos separadamente para o CAGED e para a Base_de_Municipios.
# Validates: Requirements 3.6
@given(
    codigos_caged=st.lists(
        st.one_of(_codigo_caged_valido, _codigo_caged_malformado),
        min_size=0,
        max_size=40,
    ),
    codigos_mun=st.lists(
        st.one_of(_codigo_ibge_valido, _codigo_ibge_malformado),
        min_size=0,
        max_size=30,
    ),
)
@settings(max_examples=100)
def test_chaves_malformadas_sao_excluidas_e_contadas_por_base(codigos_caged, codigos_mun):
    df_caged = _df_caged(codigos_caged)
    df_mun = _df_municipios(codigos_mun)

    resultado = juntar(df_caged, df_mun)

    # Excluídos esperados por base: códigos cuja normalização retorna None.
    caged_malformados = sum(
        1 for c in codigos_caged if chave_municipal_caged(c) is None
    )
    mun_malformados = sum(
        1 for c in codigos_mun if chave_municipal_ibge(c) is None
    )

    assert resultado.excluidos_caged == caged_malformados
    assert resultado.excluidos_municipios == mun_malformados

    # Os registros malformados não entram na junção: o total é o complemento.
    assert resultado.total_caged_valido == len(codigos_caged) - caged_malformados
    assert resultado.total_caged == len(codigos_caged)

    # Nenhuma chave no resultado é malformada (todas têm exatamente 6 dígitos).
    for chave in resultado.df["chave_municipal"].tolist():
        assert isinstance(chave, str) and len(chave) == 6 and chave.isdigit()
