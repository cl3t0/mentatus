from gqlalchemy import Memgraph
from litellm import completion
from typing import List, Tuple
import os

memgraph = Memgraph(os.environ["MEMGRAPH_HOST"], int(os.environ["MEMGRAPH_PORT"]))


def _filter_useless_info(text: str) -> str:
    return text


def _identify_entities(
    current_graph: List[Tuple[str, str, str]], text: str
) -> List[str]:
    has_graph = len(current_graph) > 0
    system_prompt = (
        "Você vai receber um texto demarcado por <TEXTO></TEXTO>. Seu objetivo é encontrar "
        "TODAS as entidades mencionadas, para que seja possível construir um grafo com "
        "todas as informações contidas no texto. Por isso, é importante que todas as informações "
        "sejam incluídas. O retorno deve "
        "ter somente as entidades separadas por vírgula, nada além disso."
    ) + (
        " Você também vai receber um grafo de conhecimento já existente demarcado por <GRAFO></GRAFO>. "
        "Caso uma determinada entidade já exista, faça questão de escrever com o nome original."
        if has_graph
        else ""
    )
    prompt = f"<GRAFO>{current_graph}</GRAFO><TEXTO>{text}</TEXTO>"
    response = completion(
        model="groq/llama-3.1-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )
    model_output = response.choices[0].message.content
    return [entity.strip() for entity in model_output.split(",")]


def _identify_edges(entities: List[str], text: str) -> List[Tuple[str, str, str]]:
    system_prompt = (
        "Você vai receber um texto demarcado por <TEXTO></TEXTO>. Seu objetivo é encontrar "
        "TODOS os relacionamentos entre as entidades demarcadas por <ENTIDADES></ENTIDADES>, "
        "para que seja possível construir um grafo com todas as informações contidas no texto. "
        "Por isso, é importante que todas as informações sejam incluídas. O retorno deve "
        "ser no seguinte formato: \n\n"
        "Pedro, é, legal\n"
        "Eu, vivo na, Alemanha\n\n"
        "OBS: Não incluir mensagem anterior ou posterior ao retorno desejado."
    )
    prompt = f"<ENTIDADES>{entities}</ENTIDADES><TEXTO>{text}</TEXTO>"
    response = completion(
        model="groq/llama-3.1-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )
    model_output = response.choices[0].message.content
    return [
        (e1, r, e2)
        for row in model_output.split("\n")
        for e1, r, e2 in [row.split(",")]
    ]


def _check_if_graph_is_complete(
    current_graph: List[Tuple[str, str, str]], text: str
) -> bool:
    system_prompt = (
        "Você vai receber um texto demarcado por <TEXTO></TEXTO>. Seu objetivo "
        "é determinar se TODAS as informações contidas no texto estão refletidas "
        "no grafo. O retorno deve ser somente Y ou N."
    )
    prompt = f"<GRAFO>{current_graph}</GRAFO><TEXTO>{text}</TEXTO>"
    response = completion(
        model="groq/llama-3.1-70b-versatile",
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": prompt,
            },
        ],
        temperature=0,
    )
    model_output = response.choices[0].message.content
    return model_output == "Y"


def _write_to_db(relationships: List[Tuple[str, str, str]]) -> None:
    for source, relation, target in relationships:
        memgraph.execute(
            f"""
                    MERGE (s:Entity {{name: '{source}'}})
                    MERGE (t:Entity {{name: '{target}'}})
                    MERGE (s)-[:{relation}]->(t)
                """
        )


def _get_from_db() -> List[Tuple[str, str, str]]:
    query = """
        MATCH (source)-[rel]->(target)
        RETURN source.name AS source_name, type(rel) AS relationship, target.name AS target_name
    """

    data = memgraph.execute_and_fetch(query)

    return [
        (record["source_name"], record["relationship"], record["target_name"])
        for record in data
    ]


def save(user_input: str) -> None:
    is_done = False
    while not is_done:
        current_graph = _get_from_db()
        is_done = _check_if_graph_is_complete(current_graph, user_input)
        filtered_input = _filter_useless_info(user_input)
        entities = _identify_entities(current_graph, filtered_input)
        relationships = _identify_edges(entities, filtered_input)
        _write_to_db(relationships)


print(
    _check_if_graph_is_complete(
        [
            ("Clube dos Sonhos", " é", " evento"),
            ("Andrey", " é", " estudante"),
            ("Maria Clara Fusco", " é", " estudante"),
            ("Davi de Freitas", " é", " estudante"),
            ("Bruna Whately", " é", " estudante"),
            ("Alpha Lumen", " é", " instituição"),
            ("Andrey", " participou do", " Clube dos Sonhos"),
            ("Maria Clara Fusco", " participou do", " Clube dos Sonhos"),
            ("Davi de Freitas", " participou do", " Clube dos Sonhos"),
            ("Bruna Whately", " participou do", " Clube dos Sonhos"),
            ("Andrey", " estudou no", " Alpha Lumen"),
            ("Maria Clara Fusco", " estudou no", " Alpha Lumen"),
            ("Davi de Freitas", " estudou no", " Alpha Lumen"),
            ("Bruna Whately", " estudou no", " Alpha Lumen"),
        ],
        """Oi, pessoal!

Queria compartilhar com vocês um vídeo que resume o evento final do Clube dos Sonhos. Nele, temos depoimentos super emocionantes dos nossos estudantes Andrey, Maria Clara Fusco, Davi de Freitas e Bruna Whately, falando sobre como a experiência no Alpha Lumen fez a diferença na vida deles.

Vale muito a pena dar uma olhada!

(https://youtu.be/9TuD31OTytI?si=tDPDPPJy3s4qoIMw)

Espero que vocês gostem tanto quanto eu gostei.""",
    )
)
