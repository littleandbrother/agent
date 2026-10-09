"""Public facts about the existing assembly validator, not design advice."""
from . import assembly


def contract():
    example={'title':'Interface example only','units':'mm','parts':[{'id':'body','name':'example envelope','role':'housing',
        'geometry':{'kind':'box','size_mm':[10,10,10],'center_mm':[0,0,0],'rotation_deg':[0,0,0]},
        'source':{'basis':'design-assumption','note':'Interface example, no source or product claim.'}}],
        'required_roles':['housing'],'requirements':[],'assumptions':[],'interfaces':[],'energy':{},'presentation':{'camera_deg':35}}
    assembly.validate(example)
    return {'schema_version':'bf-assembly-interface-v1','scope':'Input interface facts only; no product or geometry acceptance',
        'action':'assembly_write','request_fields':['assembly_path','expected_revision','operation_id','source_message_id'],
        'path_scope':'Existing UTF-8 JSON file relative to this owner workspace',
        'required_top_fields':['title','units','parts','required_roles','requirements','assumptions','interfaces','energy'],
        'units':'mm','max_parts':96,'roles':sorted(assembly.ROLES),'geometry_kinds':sorted(assembly.KINDS),
        'source_bases':['datasheet-envelope','design-assumption','native-component'],
        'source_note_required':True,'datasheet_source_url_prefix':'https://',
        'geometry_required':{'size_mm':{'length':3,'minimum':.05,'maximum':500},
            'center_mm':{'length':3,'minimum':-1000,'maximum':1000},
            'rotation_deg':{'length':3,'minimum':-360,'maximum':360}},
        'geometry_extra_constraints':['sphere has three equal size_mm values','cylinder has equal x/y size_mm',
            'shell wall_mm >= 0.5 and less than half of its smallest size','fillet_mm is nonnegative and less than half of smallest size',
            'maximum 20 cutouts, no shell or nested cutouts'],
        'presentation_camera_deg':{'minimum':-180,'maximum':180,'type':'number'},
        'energy_constraint':'Object required; this validator alone does not qualify energy parameters',
        'required_roles_constraint':'Nonempty list drawn from roles; this interface check does not prove role coverage or fit',
        'representation_boundary':'Workspace envelope limits do not change true CAD dimensions; approximations require separate explicit source records',
        'minimal_valid_example':example}
