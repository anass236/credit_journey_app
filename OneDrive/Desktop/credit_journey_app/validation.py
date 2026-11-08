"""Bounded request parsing and domain validation. No client values become SQL syntax."""
import json
import math
import re

from flask import request
from werkzeug.exceptions import BadRequest, UnsupportedMediaType

PHASES = {'Discovery', 'Application', 'Assessment', 'Contracting', 'Fulfillment', 'Lifecycle', 'Other'}


def _reject_constant(value):
    raise ValueError('Les nombres JSON doivent être finis.')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Une même clé JSON ne peut pas être répétée.')
        result[key] = value
    return result


def json_object():
    if not request.is_json:
        raise UnsupportedMediaType('Utilisez le type de contenu application/json.')
    try:
        payload = json.loads(request.get_data().decode('utf-8'), parse_constant=_reject_constant, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise BadRequest('Le contenu JSON est invalide.') from exc
    if not isinstance(payload, dict):
        raise BadRequest('Un objet JSON est requis.')
    return payload


def text(value, name, maximum, required=False):
    if not isinstance(value, str):
        raise ValueError(f'Le champ « {name} » doit contenir du texte.')
    value = value.strip()
    if (required and not value) or len(value) > maximum or any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise ValueError(f'Le champ « {name} » doit contenir de {"1" if required else "0"} à {maximum} caractères, sans caractères de contrôle.')
    return value


def identifier(value, name='Identifiant'):
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise ValueError(f'Le champ « {name} » doit être un nombre entier positif.')
    return value


def optional_identifier(value):
    return None if value is None else identifier(value)


def integer(value, name, maximum):
    if type(value) is not int or not 0 <= value <= maximum:
        raise ValueError(f'Le champ « {name} » doit être un entier compris entre 0 et {maximum}.')
    return value


def subteam(payload):
    return (identifier(payload.get('team_id'), 'Équipe parente'),
            text(payload.get('name', ''), 'Nom de la sous-équipe', 80, True),
            integer(payload.get('headcount'), 'Effectif', 10000))


def macro(payload):
    return (text(payload.get('name', ''), 'Nom de la macro-étape', 100, True),
            text(payload.get('description', ''), 'Description', 1000),
            color(payload.get('color', '#22b5be')),
            integer(payload.get('sort_order', 0), 'Ordre d’affichage', 1000))


def number(value, name, minimum, maximum):
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        raise ValueError(f'Le champ « {name} » doit être un nombre fini compris entre {minimum} et {maximum}.')
    return float(value)


def choice(value, values, name):
    if not isinstance(value, str) or value not in values:
        raise ValueError(f'La valeur du champ « {name} » est invalide.')
    return value


def color(value):
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Utilisez une couleur hexadécimale à six chiffres, précédée de #.')
    return value


def password(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError('Utilisez un mot de passe de 12 à 128 caractères.')
    return value


def credentials(payload):
    username = text(payload.get('username', ''), 'Identifiant', 50, True)
    if not re.fullmatch(r'[A-Za-z0-9_.-]{3,50}', username):
        raise ValueError('L’identifiant doit contenir de 3 à 50 lettres non accentuées, chiffres, points, tirets ou traits de soulignement.')
    return username, password(payload.get('password', ''))


def stage(payload):
    teams = payload.get('team_ids', [])
    if not isinstance(teams, list) or len(teams) > 250:
        raise ValueError('Sélectionnez au maximum 250 équipes.')
    teams = sorted({identifier(team, 'Identifiant de l’équipe') for team in teams})
    return (text(payload.get('name', ''), 'Nom de l’étape', 100, True),
            text(payload.get('description', ''), 'Description', 1000),
            choice(payload.get('phase', 'Other'), PHASES, 'phase'),
            number(payload.get('x', 100), 'X', -10000, 10000),
            number(payload.get('y', 100), 'Y', -10000, 10000), teams)


def edge(payload):
    source = identifier(payload.get('source'), 'Étape de départ')
    target = identifier(payload.get('target'), 'Étape d’arrivée')
    if source == target:
        raise ValueError('Une étape ne peut pas être reliée à elle-même.')
    return (source, target, text(payload.get('label', ''), 'Libellé', 60),
            choice(payload.get('shape', 'curved'), {'straight', 'curved', 'elbow'}, 'Tracé'),
            choice(payload.get('line_style', 'solid'), {'solid', 'dashed', 'dotted'}, 'Style du trait'),
            color(payload.get('color', '#a9c1c7')),
            number(payload.get('width', 2.3), 'Épaisseur', 1, 8),
            number(payload.get('bend', 80), 'Courbure', -300, 300))
