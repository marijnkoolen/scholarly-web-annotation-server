import json
import datetime
import pytz
import uuid
import copy
from rfc3987 import parse as parse_iri
from typing import List, Union


def validate_generic(annotation: dict) -> None:
    if type(annotation) != dict:
        raise AnnotationError(message='annotation MUST be valid JSON')
    if "@context" not in annotation:
        raise AnnotationError(message='annotation MUST have a @context')
    if annotation["@context"] != "http://www.w3.org/ns/anno.jsonld":
        raise AnnotationError(message='annotation @context MUST include "http://www.w3.org/ns/anno.jsonld"')
    if 'type' not in annotation:
        raise AnnotationError(message='annotation MUST have a type')


def as_list(value: any) -> List[any]:
    if isinstance(value, list):
        return value
    return [value]


def validate_annotation(annotation: dict):
    if "Annotation" not in as_list(annotation['type']):
        raise AnnotationError(message='annotation type MUST include "Annotation"')

    if 'target' not in annotation:
        raise AnnotationError(message='annotation MUST have at least one target')
    for target in as_list(annotation['target']):
        target_id = None
        if type(target) == str:
            target_id = target
        elif type(target) == dict:
            if 'id' in target:
                target_id = target['id']
            elif 'source' in target:
                target_id = target['source']
        else:
            # there is no identifier for the target
            raise AnnotationError(message='External annotation target MUST have an IRI identifier')
        try:
            # id must be an IRI
            parse_iri(target_id, rule="IRI")
        except ValueError:
            raise AnnotationError(message='annotation target id MUST be an IRI')


def validate_annotation_page(annotation_page: dict):
    if "AnnotationPage" not in as_list(annotation_page['type']):
        raise AnnotationError(message='annotation "type" property MUST include "AnnotationPage"')
    if "items" not in annotation_page.keys():
        raise AnnotationError(message='annotation page MUST have an "items" property with as value a list with at '
                                      'least one annotation.')
    if type(annotation_page["items"]) != list or len(annotation_page["items"]) == 0:
        raise AnnotationError(message='annotation page "items" property MUST be a list with at least one annotation.')


def validate_annotation_collection(annotation_collection: dict):
    if "AnnotationCollection" not in as_list(annotation_collection['type']):
        raise AnnotationError(message='annotation "type" property MUST include "AnnotationCollection"')
    if "label" not in annotation_collection.keys():
        raise AnnotationError(message='annotation collection MUST have an "label" property with as value a string.')
    if type(annotation_collection["label"]) != str:
        raise AnnotationError(message='annotation collection "label" property MUST be a string.')
    if "total" in annotation_collection.keys():
        if "first" not in annotation_collection.keys():
            raise AnnotationError(message='Non-empty collection MUST have "first" property referencing the first '
                                          'AnnotationPage')
        if "last" not in annotation_collection.keys():
            raise AnnotationError(message='Non-empty collection MUST have "last" property referencing the first '
                                          'AnnotationPage')


class WebAnnotationValidator(object):

    def __init__(self):
        self.accepted_types = ["Annotation", "AnnotationCollection", "AnnotationPage"]

    def validate(self, annotation: dict, annotation_type: Union[str, None] = None):
        validate_generic(annotation)
        self.validate_type(annotation, annotation_type)
        return True

    def validate_type(self, annotation: dict, annotation_type: Union[str, None]):
        anno_type = self.has_valid_type(annotation)
        if annotation_type is None:
            annotation_type = anno_type
        if annotation_type not in as_list(annotation['type']):
            raise AnnotationError(message="annotation is not of type %s" % annotation_type)
        if annotation_type == "Annotation":
            validate_annotation(annotation)
        if annotation_type == "AnnotationPage":
            validate_annotation_page(annotation)
        if annotation_type == "AnnotationCollection":
            validate_annotation_collection(annotation)

    def has_valid_type(self, annotation: dict) -> str:
        """An annotation can have multiple types, but only one of the three mutually exclusive
        annotation types."""
        types = [anno_type for anno_type in as_list(annotation["type"]) if anno_type in self.accepted_types]
        if len(types) > 1:
            raise AnnotationError(message="annotation cannot have multiple annotation types")
        if len(types) == 0:
            raise AnnotationError(message='annotation type MUST have one of "Annotation", "AnnotationCollection", '
                                          '"AnnotationPage"')
        return types[0]


class Annotation(object):

    def __init__(self, annotation: dict):
        if 'id' not in annotation:
            annotation['id'] = uuid.uuid4().urn
        if 'created' not in annotation:
            annotation['created'] = datetime.datetime.now(pytz.utc).isoformat()
        self.validator = WebAnnotationValidator()
        self.validator.validate(annotation)
        self.data = annotation
        self.type = "Annotation"
        self.id = annotation['id']
        self.motivation = annotation['motivation'] if 'motivation' in annotation else None
        self.in_collection = []
        self.permissions = None
        self.target_list = None
        self.set_permissions()
        self.set_target_list()

    def set_permissions(self) -> None:
        if "permissions" in self.data:
            self.permissions = self.data["permissions"]
            del self.data["permissions"]
        else:
            self.permissions = None

    def set_target_list(self) -> None:
        if "target_list" in self.data:
            self.target_list = self.data["target_list"]
            del self.data["target_list"]
        else:
            self.target_list = None

    def to_json(self) -> dict:
        annotation_json = copy.copy(self.data)
        annotation_json["permissions"] = self.permissions
        annotation_json["target_list"] = self.target_list
        return annotation_json

    def to_clean_json(self, params) -> dict:
        annotation_json = copy.copy(self.data)
        if params and "include_permissions" in params and params["include_permissions"]:
            annotation_json["permissions"] = self.permissions
        return annotation_json

    def get_permissions(self) -> Union[None, dict]:
        return self.permissions

    def has_target(self, target_id: str) -> bool:
        if not self.get_targets():
            return False
        for target in self.get_targets():
            if target == target_id:
                return True
            if 'id' in target['id'] == target_id:
                return True
            if 'selector' not in target or not target['selector'] or 'value' not in target['selector']:
                return False
            if target['selector']['value'] == target_id:
                return True
        return False

    def get_targets(self) -> List[Union[str, dict]]:
        if 'target' not in self.data:
            return []
        if type(self.data['target']) == list:
            return self.data['target']
        else:
            return [self.data['target']]

    def get_targets_info(self) -> List[dict]:
        return [target_info for target in self.get_targets() for target_info in self.get_target_info(target)]

    def get_target_info(self, target: dict) -> List[dict]:
        if type(target) == str:
            info = [{"id": target}]
        elif "id" in target:
            if "type" not in target:
                raise AnnotationError("target requires a type property")
            info = [{"id": target["id"], "type": target["type"]}]
        elif "source" in target and "selector" in target:
            if "type" not in target:
                raise AnnotationError("target requires a type property")
            info = [{"id": target["source"], "type": target["type"]}]
            info = self.get_selector_info(target["selector"], info)
        else:
            raise AnnotationError("target requires an id or source property")
        return info

    def get_selector_info(self, selectors: Union[None, List[dict], dict], info: List[dict]) -> List[dict]:
        if not selectors:
            return info
        if type(selectors) != list:
            selectors = [selectors]
        for selector in selectors:
            if selector["type"] == "SubresourceSelector":
                info += self.get_subresource_info(selector["value"]["subresource"])
            if selector["type"] == "NestedPIDSelector":
                info = selector["value"]
        return info

    def get_subresource_info(self, subresource):
        info = [{"id": subresource["id"], "type": subresource["type"]}]
        if "subresource" in subresource:
            info += self.get_subresource_info(subresource["subresource"])
        return info

    def get_target_ids(self) -> List[str]:
        return [target_id for target in self.get_targets() for target_id in self.get_target_id(target)]

    def get_target_id(self, target: Union[str, dict]) -> List[str]:
        if type(target) == str:
            return [target]
        if 'id' in target:
            return [target['id']]
        if 'source' in target and 'selector' in target:
            ids = [target['source']] + self.get_selector_ids(target["selector"])
            return ids

    def get_selector_ids(self, selectors: Union[None, dict, List[dict]]) -> List[str]:
        ids = []
        if not selectors:
            return ids
        if type(selectors) != list:
            selectors = [selectors]
        for selector in selectors:
            if selector["type"] == "SubresourceSelector":
                ids += self.get_subresource_ids(selector["value"]["subresource"])
            if selector["type"] == "NestedPIDSelector":
                ids += [resource["id"] for resource in selector["value"]]
        return ids

    def get_subresource_ids(self, subresource: dict) -> List[str]:
        ids = [subresource["id"]]
        if "subresource" in subresource:
            ids += self.get_subresource_ids(subresource["subresource"])
        return ids

    def update(self, updated_annotation: dict) -> None:
        self.validator.validate(updated_annotation)
        if self.id == updated_annotation['id']:
            updated_annotation['modified'] = datetime.datetime.now(pytz.utc).isoformat()
            self.data = updated_annotation
        else:
            raise AnnotationError(message="ID of updated annotation does not match ID of existing annotation")


class AnnotationError(Exception):
    status_code = 400

    def __init__(self, message, status_code=400, payload=None):
        Exception.__init__(self)
        self.message = message
        self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['message'] = self.message
        rv['status_code'] = self.status_code
        return rv


if __name__ == "__main__":
    annotations_file = "data/annotations.json"
    try:
        with open(annotations_file, 'r') as f:
            annotations = json.loads(f.read())
    except FileNotFoundError:
        annotations = []
