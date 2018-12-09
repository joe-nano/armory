import bpy
import arm.assets as assets
import arm.material.mat_state as mat_state
import arm.material.mat_utils as mat_utils
import arm.material.cycles as cycles
import arm.material.make_skin as make_skin
import arm.material.make_inst as make_inst
import arm.material.make_tess as make_tess
import arm.material.make_particle as make_particle
import arm.utils

is_displacement = False
write_material_attribs = None
write_material_attribs_post = None
write_vertex_attribs = None

def make(context_id):
    rpdat = arm.utils.get_rp()
    rid = rpdat.rp_renderer

    con = { 'name': context_id, 'depth_write': True, 'compare_mode': 'less', 'cull_mode': 'clockwise' }
    
    # Blend context
    mat = mat_state.material
    blend = mat.arm_blending
    particle = mat_state.material.arm_particle_flag
    dprepass = rid == 'Forward' and rpdat.rp_depthprepass
    if blend:
        con['name'] = 'blend'
        con['blend_source'] = mat.arm_blending_source
        con['blend_destination'] = mat.arm_blending_destination
        con['blend_operation'] = mat.arm_blending_operation
        con['alpha_blend_source'] = mat.arm_blending_source_alpha
        con['alpha_blend_destination'] = mat.arm_blending_destination_alpha
        con['alpha_blend_operation'] = mat.arm_blending_operation_alpha
        con['depth_write'] = False
        con['compare_mode'] = 'less'
    elif particle:
        pass
    elif dprepass: # Depth prepass was performed
        con['depth_write'] = False
        con['compare_mode'] = 'equal'

    con_mesh = mat_state.data.add_context(con)
    mat_state.con_mesh = con_mesh

    if rid == 'Forward' or blend:
        if rpdat.arm_material_model == 'Mobile':
            make_forward_mobile(con_mesh)
        elif rpdat.arm_material_model == 'Solid':
            make_forward_solid(con_mesh)
        else:
            make_forward(con_mesh)
    elif rid == 'Deferred':
        make_deferred(con_mesh)
    elif rid == 'Raytracer':
        make_raytracer(con_mesh)

    make_finalize(con_mesh)

    assets.vs_equal(con_mesh, assets.shader_cons['mesh_vert'])

    return con_mesh

def make_finalize(con_mesh):
    vert = con_mesh.vert
    frag = con_mesh.frag
    geom = con_mesh.geom
    tesc = con_mesh.tesc
    tese = con_mesh.tese

    # Additional values referenced in cycles
    # TODO: enable from cycles.py
    if frag.contains('dotNV') and not frag.contains('float dotNV'):
        frag.write_init('float dotNV = max(dot(n, vVec), 0.0);')
    
    write_wpos = False
    if frag.contains('vVec') and not frag.contains('vec3 vVec'):
        if tese != None:
            tese.add_out('vec3 eyeDir')
            tese.add_uniform('vec3 eye', '_cameraPosition')
            tese.write('eyeDir = eye - wposition;')

        else:
            if not vert.contains('wposition'):
                write_wpos = True
            vert.add_out('vec3 eyeDir')
            vert.add_uniform('vec3 eye', '_cameraPosition')
            vert.write('eyeDir = eye - wposition;')
        frag.write_attrib('vec3 vVec = normalize(eyeDir);')
    
    export_wpos = False
    if frag.contains('wposition') and not frag.contains('vec3 wposition'):
        export_wpos = True
    if tese != None:
        export_wpos = True
    if vert.contains('wposition'):
        write_wpos = True
    
    if export_wpos:
        vert.add_uniform('mat4 W', '_worldMatrix')
        vert.add_out('vec3 wposition')
        vert.write_attrib('wposition = vec4(W * spos).xyz;')
    elif write_wpos:
        vert.add_uniform('mat4 W', '_worldMatrix')
        vert.write_attrib('vec3 wposition = vec4(W * spos).xyz;')

    frag_mpos = (frag.contains('mposition') and not frag.contains('vec3 mposition')) or vert.contains('mposition')
    if frag_mpos:
        vert.add_out('vec3 mposition')
        vert.write_attrib('mposition = spos.xyz;')
    
    if tese != None:
        if frag_mpos:
            make_tess.interpolate(tese, 'mposition', 3, declare_out=True)
        elif tese.contains('mposition') and not tese.contains('vec3 mposition'):
            vert.add_out('vec3 mposition')
            vert.write_pre = True
            vert.write('mposition = spos.xyz;')
            vert.write_pre = False
            make_tess.interpolate(tese, 'mposition', 3, declare_out=False)

    frag_bpos = (frag.contains('bposition') and not frag.contains('vec3 bposition')) or vert.contains('bposition')
    if frag_bpos:
        vert.add_out('vec3 bposition')
        vert.add_uniform('vec3 dim', link='_dim')
        vert.add_uniform('vec3 hdim', link='_halfDim')
        vert.write_pre = True
        vert.write('bposition = (spos.xyz + hdim) / dim;')
        vert.write_pre = False
    
    if tese != None:
        if frag_bpos:
            make_tess.interpolate(tese, 'bposition', 3, declare_out=True)
        elif tese.contains('bposition') and not tese.contains('vec3 bposition'):
            vert.add_out('vec3 bposition')
            vert.write_pre = True
            vert.write('bposition = spos.xyz;')
            vert.write_pre = False
            make_tess.interpolate(tese, 'bposition', 3, declare_out=False)

    frag_wtan = (frag.contains('wtangent') and not frag.contains('vec3 wtangent')) or vert.contains('wtangent')
    if frag_wtan:
        # Indicate we want tang attrib in finalizer to prevent TBN generation
        con_mesh.add_elem('tex', 2)
        con_mesh.add_elem('tang', 3)
        vert.add_out('vec3 wtangent')
        vert.write_pre = True
        vert.write('wtangent = normalize(N * tang);')
        vert.write_pre = False

    if tese != None:
        if frag_wtan:
            make_tess.interpolate(tese, 'wtangent', 3, declare_out=True)
        elif tese.contains('wtangent') and not tese.contains('vec3 wtangent'):
            vert.add_out('vec3 wtangent')
            vert.write_pre = True
            vert.write('wtangent = normalize(N * tang);')
            vert.write_pre = False
            make_tess.interpolate(tese, 'wtangent', 3, declare_out=False)

    if frag.contains('vVecCam'):
        vert.add_out('vec3 eyeDirCam')
        vert.add_uniform('mat4 WV', '_worldViewMatrix')
        vert.write('eyeDirCam = vec4(WV * spos).xyz; eyeDirCam.z *= -1;')
        frag.write_attrib('vec3 vVecCam = normalize(eyeDirCam);')

def make_base(con_mesh, parse_opacity):
    global is_displacement
    global write_material_attribs
    global write_material_attribs_post
    global write_vertex_attribs

    vert = con_mesh.make_vert()
    frag = con_mesh.make_frag()
    geom = None
    tesc = None
    tese = None

    vert.add_uniform('mat3 N', '_normalMatrix')
    vert.write_attrib('vec4 spos = vec4(pos, 1.0);')

    vattr_written = False
    rpdat = arm.utils.get_rp()
    is_displacement = mat_utils.disp_linked(mat_state.output_node)
    if is_displacement:
        if rpdat.arm_rp_displacement == 'Vertex':
            frag.ins = vert.outs
        else: # Tessellation
            tesc = con_mesh.make_tesc()
            tese = con_mesh.make_tese()
            tesc.ins = vert.outs
            tese.ins = tesc.outs
            frag.ins = tese.outs
            make_tess.tesc_levels(tesc, rpdat.arm_tess_mesh_inner, rpdat.arm_tess_mesh_outer)
            make_tess.interpolate(tese, 'wposition', 3, declare_out=True)
            make_tess.interpolate(tese, 'wnormal', 3, declare_out=True, normalize=True)
    # No displacement
    else:
        frag.ins = vert.outs
        if write_vertex_attribs != None:
            vattr_written = write_vertex_attribs(vert)

    frag.add_include('compiled.inc')

    written = False
    if write_material_attribs != None:
        written = write_material_attribs(con_mesh, frag)
    if written == False:
        frag.write('vec3 basecol;')
        frag.write('float roughness;')
        frag.write('float metallic;')
        frag.write('float occlusion;')
        frag.write('float specular;')
        if parse_opacity:
            frag.write('float opacity;')
        cycles.parse(mat_state.nodes, con_mesh, vert, frag, geom, tesc, tese, parse_opacity=parse_opacity)
    if write_material_attribs_post != None:
        write_material_attribs_post(con_mesh, frag)

    if not is_displacement and not vattr_written:
        write_vertpos(vert)

    if con_mesh.is_elem('tex'):
        vert.add_out('vec2 texCoord')
        if mat_state.material.arm_tilesheet_mat:
            if mat_state.material.arm_particle_flag and rpdat.arm_particles == 'GPU':
                make_particle.write_tilesheet(vert)
            else:
                vert.add_uniform('vec2 tilesheetOffset', '_tilesheetOffset')
                vert.write_attrib('texCoord = tex + tilesheetOffset;')
        else:
            vert.write_attrib('texCoord = tex;')

        if tese != None:
            tese.write_pre = True
            make_tess.interpolate(tese, 'texCoord', 2, declare_out=frag.contains('texCoord'))
            tese.write_pre = False

    if con_mesh.is_elem('tex1'):
        vert.add_out('vec2 texCoord1')
        vert.write_attrib('texCoord1 = tex1;')
        if tese != None:
            tese.write_pre = True
            make_tess.interpolate(tese, 'texCoord1', 2, declare_out=frag.contains('texCoord1'))
            tese.write_pre = False

    if con_mesh.is_elem('col'):
        vert.add_out('vec3 vcolor')
        vert.write_attrib('vcolor = col;')
        if tese != None:
            tese.write_pre = True
            make_tess.interpolate(tese, 'vcolor', 3, declare_out=frag.contains('vcolor'))
            tese.write_pre = False

    if con_mesh.is_elem('tang'):
        if tese != None:
            vert.add_out('vec3 wnormal')
            write_norpos(con_mesh, vert)
            tese.add_out('mat3 TBN')
            tese.write('vec3 wbitangent = normalize(cross(wnormal, wtangent));')
            tese.write('TBN = mat3(wtangent, wbitangent, wnormal);')
        else:
            vert.add_out('mat3 TBN')
            write_norpos(con_mesh, vert, declare=True)
            vert.write('vec3 tangent = normalize(N * tang);')
            vert.write('vec3 bitangent = normalize(cross(wnormal, tangent));')
            vert.write('TBN = mat3(tangent, bitangent, wnormal);')
    else:
        vert.add_out('vec3 wnormal')
        write_norpos(con_mesh, vert)
        frag.write_attrib('vec3 n = normalize(wnormal);')

    if is_displacement:
        if rpdat.arm_rp_displacement == 'Vertex':
            sh = vert
        else:
            sh = tese
        sh.add_uniform('mat4 VP', '_viewProjectionMatrix')
        sh.write('wposition += wnormal * disp * 0.1;')
        sh.write('gl_Position = VP * vec4(wposition, 1.0);')

def write_vertpos(vert):
    billboard = mat_state.material.arm_billboard
    particle = mat_state.material.arm_particle_flag
    # Particles
    if particle:
        if arm.utils.get_rp().arm_particles == 'GPU':
            make_particle.write(vert, particle_info=cycles.particle_info)
        # Billboards
        if billboard == 'spherical':
            vert.add_uniform('mat4 WV', '_worldViewMatrix')
            vert.add_uniform('mat4 P', '_projectionMatrix')
            vert.write('gl_Position = P * (WV * vec4(0.0, 0.0, spos.z, 1.0) + vec4(spos.x, spos.y, 0.0, 0.0));')
        else:
            vert.add_uniform('mat4 WVP', '_worldViewProjectionMatrix')
            vert.write('gl_Position = WVP * spos;')
    else:
        # Billboards
        if billboard == 'spherical':
            vert.add_uniform('mat4 WVP', '_worldViewProjectionMatrixSphere')
        elif billboard == 'cylindrical':
            vert.add_uniform('mat4 WVP', '_worldViewProjectionMatrixCylinder')
        else: # off
            vert.add_uniform('mat4 WVP', '_worldViewProjectionMatrix')
        vert.write('gl_Position = WVP * spos;')

def write_norpos(con_mesh, vert, declare=False, write_nor=True):
    prep = ''
    if declare:
        prep = 'vec3 '
    vert.write_pre = True
    is_bone = con_mesh.is_elem('bone')
    if is_bone:
        make_skin.skin_pos(vert)
    if write_nor:
        if is_bone:
            make_skin.skin_nor(vert, prep)
        else:
            vert.write(prep + 'wnormal = normalize(N * nor);')
    if con_mesh.is_elem('ipos'):
        make_inst.inst_pos(con_mesh, vert)
    vert.write_pre = False

def make_deferred(con_mesh):
    wrd = bpy.data.worlds['Arm']
    rpdat = arm.utils.get_rp()

    arm_discard = mat_state.material.arm_discard
    parse_opacity = arm_discard

    make_base(con_mesh, parse_opacity=parse_opacity)

    frag = con_mesh.frag
    vert = con_mesh.vert
    tese = con_mesh.tese

    if arm_discard:
        opac = mat_state.material.arm_discard_opacity
        frag.write('if (opacity < {0}) discard;'.format(opac))

    gapi = arm.utils.get_gapi()
    if '_gbuffer2' in wrd.world_defs:
        frag.add_out('vec4[3] fragColor')
        if '_Veloc' in wrd.world_defs:
            if tese == None:
                vert.add_uniform('mat4 prevWVP', link='_prevWorldViewProjectionMatrix')
                vert.add_out('vec4 wvpposition')
                vert.add_out('vec4 prevwvpposition')
                vert.write('wvpposition = gl_Position;')
                if is_displacement:
                    vert.add_uniform('mat4 invW', link='_inverseWorldMatrix')
                    vert.write('prevwvpposition = prevWVP * (invW * vec4(wposition, 1.0));')
                else:
                    vert.write('prevwvpposition = prevWVP * spos;')
            else:
                tese.add_out('vec4 wvpposition')
                tese.add_out('vec4 prevwvpposition')
                tese.write('wvpposition = gl_Position;')
                if is_displacement:
                    tese.add_uniform('mat4 invW', link='_inverseWorldMatrix')
                    tese.add_uniform('mat4 prevWVP', '_prevWorldViewProjectionMatrix')
                    tese.write('prevwvpposition = prevWVP * (invW * vec4(wposition, 1.0));')
                else:
                    vert.add_uniform('mat4 prevW', link='_prevWorldMatrix')
                    vert.add_out('vec3 prevwposition')
                    vert.write('prevwposition = vec4(prevW * spos).xyz;')
                    tese.add_uniform('mat4 prevVP', '_prevViewProjectionMatrix')
                    make_tess.interpolate(tese, 'prevwposition', 3)
                    tese.write('prevwvpposition = prevVP * vec4(prevwposition, 1.0);')
                
    elif gapi.startswith('direct3d'):
        vert.add_out('vec4 wvpposition')
        vert.write('wvpposition = gl_Position;')
        frag.add_out('vec4[2] fragColor')
    else:
        frag.add_out('vec4[2] fragColor')

    # Pack gbuffer
    frag.add_include('std/gbuffer.glsl')

    if mat_state.material.arm_two_sided:
        frag.write('if (!gl_FrontFacing) n *= -1;') # Flip normal when drawing back-face

    frag.write('n /= (abs(n.x) + abs(n.y) + abs(n.z));')
    frag.write('n.xy = n.z >= 0.0 ? n.xy : octahedronWrap(n.xy);')
    frag.write('fragColor[0] = vec4(n.xy, packFloat(metallic, roughness), 1.0);')
    frag.write('fragColor[1] = vec4(basecol.rgb, packFloat2(occlusion, specular));')

    if '_gbuffer2' in wrd.world_defs:
        if '_Veloc' in wrd.world_defs:
            frag.write('vec2 posa = (wvpposition.xy / wvpposition.w) * 0.5 + 0.5;')
            frag.write('vec2 posb = (prevwvpposition.xy / prevwvpposition.w) * 0.5 + 0.5;')
            frag.write('fragColor[2].rg = vec2(posa - posb);')
        if '_SSS' in wrd.world_defs or '_Hair' in wrd.world_defs:
            frag.add_uniform('int materialID')
            frag.write('fragColor[2].a = materialID;')

    return con_mesh

def make_raytracer(con_mesh):
    wrd = bpy.data.worlds['Arm']
    vert = con_mesh.make_vert()
    frag = con_mesh.make_frag()
    vert.add_out('vec3 n')
    vert.write('n = nor;')
    vert.write('gl_Position = vec4(pos, 1.0);')

def make_forward_mobile(con_mesh):
    wrd = bpy.data.worlds['Arm']
    vert = con_mesh.make_vert()
    frag = con_mesh.make_frag()
    geom = None
    tesc = None
    tese = None

    vert.add_uniform('mat3 N', '_normalMatrix')
    vert.write_attrib('vec4 spos = vec4(pos, 1.0);')
    frag.ins = vert.outs

    write_vertpos(vert)

    frag.add_include('compiled.inc')
    frag.write('vec3 basecol;')
    frag.write('float roughness;')
    frag.write('float metallic;')
    frag.write('float occlusion;')
    frag.write('float specular;')

    arm_discard = mat_state.material.arm_discard
    blend = mat_state.material.arm_blending
    is_transluc = mat_utils.is_transluc(mat_state.material)
    parse_opacity = (blend and is_transluc) or arm_discard
    if parse_opacity:
        frag.write('float opacity;')

    cycles.parse(mat_state.nodes, con_mesh, vert, frag, geom, tesc, tese, parse_opacity=parse_opacity, parse_displacement=False)

    if arm_discard:
        opac = mat_state.material.arm_discard_opacity
        frag.write('if (opacity < {0}) discard;'.format(opac))

    if con_mesh.is_elem('tex'):
        vert.add_out('vec2 texCoord')
        if mat_state.material.arm_tilesheet_mat:
            vert.add_uniform('vec2 tilesheetOffset', '_tilesheetOffset')
            vert.write('texCoord = tex + tilesheetOffset;')
        else:
            vert.write('texCoord = tex;')

    if con_mesh.is_elem('col'):
        vert.add_out('vec3 vcolor')
        vert.write('vcolor = col;')

    if con_mesh.is_elem('tang'):
        vert.add_out('mat3 TBN')
        write_norpos(con_mesh, vert, declare=True)
        vert.write('vec3 tangent = normalize(N * tang);')
        vert.write('vec3 bitangent = normalize(cross(wnormal, tangent));')
        vert.write('TBN = mat3(tangent, bitangent, wnormal);')
    else:
        vert.add_out('vec3 wnormal')
        write_norpos(con_mesh, vert)
        frag.write_attrib('vec3 n = normalize(wnormal);')

    frag.add_include('std/math.glsl')
    frag.add_include('std/brdf.glsl')

    frag.add_out('vec4 fragColor')
    blend = mat_state.material.arm_blending
    if blend:
        if parse_opacity:
            frag.write('fragColor = vec4(basecol, opacity);')
        else:
            frag.write('fragColor = vec4(basecol, 1.0);')
        return

    is_shadows = '_ShadowMap' in wrd.world_defs
    if is_shadows:
        frag.add_include('std/shadows.glsl')

    frag.write('vec3 direct = vec3(0.0);')

    if '_Sun' in wrd.world_defs:
        frag.add_uniform('vec3 sunCol', '_sunColor')
        frag.add_uniform('vec3 sunDir', '_sunDirection')
        frag.write('float svisibility = 1.0;')
        frag.write('float sdotNL = max(dot(n, sunDir), 0.0);')
        if is_shadows:
            vert.add_out('vec4 lightPosition')
            vert.add_uniform('mat4 LWVP', '_biasLightWorldViewProjectionMatrix')
            vert.write('lightPosition = LWVP * spos;')            
            frag.add_uniform('sampler2D shadowMap')
            frag.add_uniform('float shadowsBias', '_sunShadowsBias')
            frag.write('if (lightPosition.w > 0.0) {')
            frag.write('    vec3 lPos = lightPosition.xyz / lightPosition.w;')
            frag.write('    const float texelSize = 1.0 / shadowmapSize.x;')
            frag.write('    svisibility = 0.0;')
            frag.write('    svisibility += float(texture(shadowMap, lPos.xy).r + shadowsBias > lPos.z);')
            frag.write('    svisibility += float(texture(shadowMap, lPos.xy + vec2(texelSize, 0.0)).r + shadowsBias > lPos.z) * 0.5;')
            frag.write('    svisibility += float(texture(shadowMap, lPos.xy + vec2(-texelSize, 0.0)).r + shadowsBias > lPos.z) * 0.25;')
            frag.write('    svisibility += float(texture(shadowMap, lPos.xy + vec2(0.0, texelSize)).r + shadowsBias > lPos.z) * 0.5;')
            frag.write('    svisibility += float(texture(shadowMap, lPos.xy + vec2(0.0, -texelSize)).r + shadowsBias > lPos.z) * 0.25;')
            frag.write('    svisibility /= 2.5;')
            frag.write('    svisibility = max(svisibility, 0.2);')
            # frag.write('    svisibility = max(float(texture(shadowMap, lPos.xy).r + shadowsBias > lPos.z), 0.5);')
            frag.write('}')
        frag.write('direct += basecol * sdotNL * sunCol * svisibility;')

    if '_Clusters' in wrd.world_defs and '_Sun' not in wrd.world_defs:
        frag.add_include('std/clusters.glsl')
        frag.add_uniform('vec3 lightPos', '_lightPosition')
        frag.add_uniform('vec3 lightCol', '_lightColor')
        frag.add_uniform('vec3 lightDir', '_lightDirection')
        frag.write('float visibility = 1.0;')
        frag.write('float dotNL = max(dot(n, lightDir), 0.0);')
        if is_shadows:
            vert.add_out('vec4 lightPosition')
            vert.add_uniform('mat4 LWVP', '_biasLightWorldViewProjectionMatrix')
            vert.write('lightPosition = LWVP * spos;')            
            frag.add_uniform('sampler2D shadowMap0')
            frag.add_uniform('float shadowsBias', '_lightShadowsBias')
            frag.write('if (lightPosition.w > 0.0) {')
            frag.write('    vec3 lPos = lightPosition.xyz / lightPosition.w;')
            frag.write('    const float texelSize = 1.0 / shadowmapSize.x;')
            frag.write('    visibility = 0.0;')
            frag.write('    visibility += float(texture(shadowMap0, lPos.xy).r + shadowsBias > lPos.z);')
            frag.write('    visibility += float(texture(shadowMap0, lPos.xy + vec2(texelSize, 0.0)).r + shadowsBias > lPos.z) * 0.5;')
            frag.write('    visibility += float(texture(shadowMap0, lPos.xy + vec2(-texelSize, 0.0)).r + shadowsBias > lPos.z) * 0.25;')
            frag.write('    visibility += float(texture(shadowMap0, lPos.xy + vec2(0.0, texelSize)).r + shadowsBias > lPos.z) * 0.5;')
            frag.write('    visibility += float(texture(shadowMap0, lPos.xy + vec2(0.0, -texelSize)).r + shadowsBias > lPos.z) * 0.25;')
            frag.write('    visibility /= 2.5;')
            frag.write('    visibility = max(visibility, 0.2);')
            # frag.write('    visibility = max(float(texture(shadowMap0, lPos.xy).r + shadowsBias > lPos.z), 0.5);')
            frag.write('}')
        frag.write('direct += basecol * dotNL * lightCol * attenuate(distance(wposition, lightPos)) * visibility;')
        # frag.write('direct += vec3(D_Approx(max(roughness, 0.3), dot(reflect(-vVec, n), lightDir)));')

    if '_Irr' in wrd.world_defs:
        frag.add_include('std/shirr.glsl')
        frag.add_uniform('vec4 shirr[7]', link='_envmapIrradiance', included=True)
        env_str = 'shIrradiance(n)'
    else:
        env_str = '0.5'

    frag.add_uniform('float envmapStrength', link='_envmapStrength')
    frag.write('fragColor = vec4(direct + basecol * {0} * envmapStrength, 1.0);'.format(env_str))

    if '_LDR' in wrd.world_defs:
        frag.write('fragColor.rgb = pow(fragColor.rgb, vec3(1.0 / 2.2));')

def make_forward_solid(con_mesh):
    wrd = bpy.data.worlds['Arm']
    vert = con_mesh.make_vert()
    frag = con_mesh.make_frag()
    geom = None
    tesc = None
    tese = None

    for e in con_mesh.data['vertex_structure']:
        if e['name'] == 'nor':
            con_mesh.data['vertex_structure'].remove(e)
            break

    vert.write_attrib('vec4 spos = vec4(pos, 1.0);')
    frag.ins = vert.outs

    write_vertpos(vert)

    frag.add_include('compiled.inc')
    frag.write('vec3 basecol;')
    frag.write('float roughness;')
    frag.write('float metallic;')
    frag.write('float occlusion;')
    frag.write('float specular;')

    arm_discard = mat_state.material.arm_discard
    blend = mat_state.material.arm_blending
    is_transluc = mat_utils.is_transluc(mat_state.material)
    parse_opacity = (blend and is_transluc) or arm_discard
    if parse_opacity:
        frag.write('float opacity;')
    
    cycles.parse(mat_state.nodes, con_mesh, vert, frag, geom, tesc, tese, parse_opacity=parse_opacity, parse_displacement=False, basecol_only=True)

    if arm_discard:
        opac = mat_state.material.arm_discard_opacity
        frag.write('if (opacity < {0}) discard;'.format(opac))

    if con_mesh.is_elem('tex'):
        vert.add_out('vec2 texCoord')
        if mat_state.material.arm_tilesheet_mat:
            vert.add_uniform('vec2 tilesheetOffset', '_tilesheetOffset')
            vert.write('texCoord = tex + tilesheetOffset;')
        else:
            vert.write('texCoord = tex;')

    if con_mesh.is_elem('col'):
        vert.add_out('vec3 vcolor')
        vert.write('vcolor = col;')

    write_norpos(con_mesh, vert, write_nor=False)

    frag.add_out('vec4 fragColor')
    if blend and parse_opacity:
        frag.write('fragColor = vec4(basecol, opacity);')
    else:
        frag.write('fragColor = vec4(basecol, 1.0);')

    if '_LDR' in wrd.world_defs:
        frag.write('fragColor.rgb = pow(fragColor.rgb, vec3(1.0 / 2.2));')

def make_forward(con_mesh):
    wrd = bpy.data.worlds['Arm']
    blend = mat_state.material.arm_blending
    parse_opacity = blend and mat_utils.is_transluc(mat_state.material)
    
    make_forward_base(con_mesh, parse_opacity=parse_opacity)

    frag = con_mesh.frag

    if not blend:
        frag.add_out('vec4 fragColor')
        frag.write('fragColor = vec4(direct + indirect, 1.0);')
    
        if '_LDR' in wrd.world_defs:
            frag.add_include('std/tonemap.glsl')
            frag.write('fragColor.rgb = tonemapFilmic(fragColor.rgb);')
            # frag.write('fragColor.rgb = pow(fragColor.rgb, vec3(1.0 / 2.2));')

    # Particle opacity
    if mat_state.material.arm_particle_flag and arm.utils.get_rp().arm_particles == 'GPU' and mat_state.material.arm_particle_fade:
        frag.write('fragColor.rgb *= p_fade;')

def make_forward_base(con_mesh, parse_opacity=False):
    global is_displacement
    wrd = bpy.data.worlds['Arm']

    arm_discard = mat_state.material.arm_discard
    make_base(con_mesh, parse_opacity=(parse_opacity or arm_discard))

    vert = con_mesh.vert
    frag = con_mesh.frag
    tese = con_mesh.tese

    if arm_discard:
        opac = mat_state.material.arm_discard_opacity
        frag.write('if (opacity < {0}) discard;'.format(opac))

    blend = mat_state.material.arm_blending
    if blend:
        frag.add_out('vec4 fragColor')
        if parse_opacity:
            frag.write('fragColor = vec4(basecol, opacity);')
        else:
            # frag.write('fragColor = vec4(basecol * lightCol * visibility, 1.0);')
            frag.write('fragColor = vec4(basecol, 1.0);')
        # TODO: Fade out fragments near depth buffer here
        return

    frag.write_init("""
    vec3 vVec = normalize(eyeDir);
    float dotNV = max(dot(n, vVec), 0.0);
""")

    sh = tese if tese != None else vert
    sh.add_out('vec3 eyeDir')
    sh.add_uniform('vec3 eye', '_cameraPosition')
    sh.write('eyeDir = eye - wposition;')

    frag.add_include('compiled.inc')
    frag.add_include('std/brdf.glsl')
    frag.add_include('std/math.glsl')

    is_shadows = '_ShadowMap' in wrd.world_defs
    if is_shadows:
        frag.add_include('std/shadows.glsl')

    frag.write('vec3 albedo = surfaceAlbedo(basecol, metallic);')
    frag.write('vec3 f0 = surfaceF0(basecol, metallic);')
    frag.write('vec3 direct = vec3(0.0);')
    frag.add_uniform('bool receiveShadow')

    if '_Sun' in wrd.world_defs:
        frag.add_uniform('vec3 sunCol', '_sunColor')
        frag.add_uniform('vec3 sunDir', '_sunDirection')
        frag.write('float svisibility = 1.0;')
        frag.write('vec3 sh = normalize(vVec + sunDir);')
        frag.write('float sdotNL = dot(n, sunDir);')
        frag.write('float sdotNH = dot(n, sh);')
        frag.write('float sdotVH = dot(vVec, sh);')
        if is_shadows:
            frag.add_uniform('sampler2D shadowMap')
            frag.add_uniform('float shadowsBias', '_sunShadowsBias')
            frag.write('if (receiveShadow) {')
            if '_CSM' in wrd.world_defs:
                frag.add_uniform('vec4 casData[shadowmapCascades * 4 + 4]', '_cascadeData', included=True)
                frag.add_uniform('vec3 eye', '_cameraPosition')
                frag.write('vec2 smSize;')
                frag.write('vec3 lPos;')
                frag.write('int casi;')
                frag.write('int casindex;')
                frag.write('mat4 LWVP = getCascadeMat(distance(eye, wposition), casi, casindex);')
                frag.write('vec4 lightPosition = LWVP * vec4(wposition, 1.0);')
                frag.write('lPos = lightPosition.xyz / lightPosition.w;')
                frag.write('smSize = shadowmapSize * vec2(shadowmapCascades, 1.0);')
            else:
                if tese != None:
                    tese.add_out('vec4 lightPosition')
                    tese.add_uniform('mat4 LVP', '_biasLightViewProjectionMatrix')
                    tese.write('lightPosition = LVP * vec4(wposition, 1.0);')
                else:
                    if is_displacement:
                        vert.add_out('vec4 lightPosition')
                        vert.add_uniform('mat4 LVP', '_biasLightViewProjectionMatrix')
                        vert.write('lightPosition = LVP * vec4(wposition, 1.0);')
                    else:
                        vert.add_out('vec4 lightPosition')
                        vert.add_uniform('mat4 LWVP', '_biasLightWorldViewProjectionMatrix')
                        vert.write('lightPosition = LWVP * spos;')
                frag.write('vec3 lPos = lightPosition.xyz / lightPosition.w;')
                frag.write('const vec2 smSize = shadowmapSize;')
            frag.write('svisibility = PCF(shadowMap, lPos.xy, lPos.z - shadowsBias, smSize);')
            frag.write('}') # receiveShadow
        # is_shadows
        frag.write('direct += (lambertDiffuseBRDF(albedo, sdotNL) + specularBRDF(f0, roughness, sdotNL, sdotNH, dotNV, sdotVH) * specular) * sunCol * svisibility;')
        # sun

    if '_Clusters' in wrd.world_defs:
        frag.add_include('std/clusters.glsl')
        frag.add_uniform('vec2 cameraProj', link='_cameraPlaneProj')
        frag.add_uniform('vec2 cameraPlane', link='_cameraPlane')
        frag.add_uniform('vec4 lightsArray[maxLights * 2]', link='_lightsArray')
        frag.add_uniform('sampler2D clustersData', link='_clustersData')
        vert.add_out('vec4 wvpposition')
        vert.write('wvpposition = gl_Position;')
        # wvpposition.z / wvpposition.w
        frag.write('float viewz = linearize(gl_FragCoord.z, cameraProj);')
        frag.write('int clusterI = getClusterI((wvpposition.xy / wvpposition.w) * 0.5 + 0.5, viewz, cameraPlane);')
        frag.write('int numLights = int(texelFetch(clustersData, ivec2(clusterI, 0), 0).r * 255);')

        frag.write('#ifdef HLSL')
        frag.write('viewz += texture(clustersData, vec2(0.0)).r * 1e-9;') # TODO: krafix bug, needs to generate sampler
        frag.write('#endif')

        frag.write('for (int i = 0; i < min(numLights, maxLightsCluster); i++) {')
        frag.write('int li = int(texelFetch(clustersData, ivec2(clusterI, i + 1), 0).r * 255);')
        frag.write('vec3 lp = lightsArray[li * 2].xyz;')
        frag.write('vec3 ld = lp - wposition;')
        frag.write('vec3 l = normalize(ld);')
        frag.write('vec3 h = normalize(vVec + l);')
        frag.write('float dotNH = dot(n, h);')
        frag.write('float dotVH = dot(vVec, h);')
        frag.write('float dotNL = dot(n, l);')
        frag.write('float visibility = attenuate(distance(wposition, lp));')

        if is_shadows:
            frag.write('float bias = lightsArray[li * 2].w;')
            if '_ShadowMapCube' in wrd.world_defs:
                frag.add_uniform('vec2 lightProj', '_lightPlaneProj')
                frag.add_uniform('samplerCube shadowMap0')
                frag.write('visibility *= PCFCube(shadowMap0, ld, -l, bias, lightProj, n);')
            else:
                frag.add_uniform('sampler2D shadowMap0')
                # frag.add_uniform('mat4 LWVP0;', link='_')
                frag.write('vec4 lPos = LWVP0 * vec4(wposition + n * bias * 10, 1.0);')
                frag.write('if (lPos.w > 0.0) {')
                #ifdef _SMSizeUniform
                #visibility *= shadowTest(shadowMap0, lPos.xyz / lPos.w, bias, smSizeUniform);
                #else
                frag.write('visibility *= shadowTest(shadowMap0, lPos.xyz / lPos.w, bias, shadowmapSize);')
                #endif
                frag.write('}')

        frag.write('direct += (lambertDiffuseBRDF(albedo, dotNL) +')
        frag.write('    specularBRDF(f0, roughness, dotNL, dotNH, dotNV, dotVH) * specular) *')
        frag.write('    visibility * lightsArray[li * 2 + 1].xyz;')

        frag.write('}') # numLights


        # Single point lamp
        # frag.add_uniform('vec3 lightCol', '_lightColor')
        # frag.add_uniform('vec3 lightPos', '_lightPosition')
        # frag.write('float visibility = 1.0;')
        # frag.write('vec3 ld = lightPos - wposition;')
        # frag.write('vec3 l = normalize(ld);')
        # frag.write('vec3 h = normalize(vVec + l);')
        # frag.write('float dotNL = dot(n, l);')
        # frag.write('float dotNH = dot(n, h);')
        # frag.write('float dotVH = dot(vVec, h);')
        # frag.write('visibility *= attenuate(distance(wposition, lightPos));')
    
        # if is_shadows:
        #     if tese != None:
        #         tese.add_out('vec4 lightPosition')
        #         tese.add_uniform('mat4 LVP', '_biasLightViewProjectionMatrix')
        #         tese.write('lightPosition = LVP * vec4(wposition, 1.0);')
        #     else:
        #         if is_displacement:
        #             vert.add_out('vec4 lightPosition')
        #             vert.add_uniform('mat4 LVP', '_biasLightViewProjectionMatrix')
        #             vert.write('lightPosition = LVP * vec4(wposition, 1.0);')
        #         else:
        #             vert.add_out('vec4 lightPosition')
        #             vert.add_uniform('mat4 LWVP', '_biasLightWorldViewProjectionMatrix')
        #             vert.write('lightPosition = LWVP * spos;')
            
        #     frag.add_uniform('samplerCube shadowMap0')
        #     frag.add_uniform('float shadowsBias', '_lightShadowsBias')
        #     frag.add_uniform('vec2 lightProj', '_lightPlaneProj')
        #     frag.write('if (receiveShadow) {')
        #     frag.write('visibility *= PCFCube(shadowMap0, ld, -l, shadowsBias, lightProj, n);')
        #     frag.write('}')

        # frag.write('direct += (lambertDiffuseBRDF(albedo, dotNL) + specularBRDF(f0, roughness, dotNL, dotNH, dotNV, dotVH) * specular) * visibility * lightCol;')


        # frag.write('if (lightType == 2) {')
        # frag.write('    float spotEffect = dot(lightDir, l);')
        # frag.write('    if (spotEffect < spotlightData.x) {')
        # frag.write('        visibility *= smoothstep(spotlightData.y, spotlightData.x, spotEffect);')
        # frag.write('    }')
        # frag.write('}')

        # if '_LTC' in wrd.world_defs:
        #     frag.add_include('std/ltc.glsl')
        #     frag.add_uniform('sampler2D sltcMat', link='_ltcMat')
        #     frag.add_uniform('sampler2D sltcMag', link='_ltcMag')
        #     frag.add_uniform('vec3 lightArea0', link='_lightArea0')
        #     frag.add_uniform('vec3 lightArea1', link='_lightArea1')
        #     frag.add_uniform('vec3 lightArea2', link='_lightArea2')
        #     frag.add_uniform('vec3 lightArea3', link='_lightArea3')
        #     frag.write('if (lightType == 3) {')
        #     frag.write('    float theta = acos(dotNV);')
        #     frag.write('    vec2 tuv = vec2(roughness, theta / (0.5 * PI));')
        #     frag.write('    tuv = tuv * LUT_SCALE + LUT_BIAS;')
        #     frag.write('    vec4 t = texture(sltcMat, tuv);')
        #     frag.write('    mat3 invM = mat3(vec3(1.0, 0.0, t.y), vec3(0.0, t.z, 0.0), vec3(t.w, 0.0, t.x));')
        #     frag.write('    float ltcspec = ltcEvaluate(n, vVec, dotNV, wposition, invM, lightArea0, lightArea1, lightArea2, lightArea3);')
        #     frag.write('    ltcspec *= texture(sltcMag, tuv).a;')
        #     frag.write('    float ltcdiff = ltcEvaluate(n, vVec, dotNV, wposition, mat3(1.0), lightArea0, lightArea1, lightArea2, lightArea3);')
        #     frag.write('    direct = albedo * ltcdiff + ltcspec * specular;')
        #     frag.write('}')

    if '_Brdf' in wrd.world_defs:
        frag.add_uniform('sampler2D senvmapBrdf', link='_envmapBrdf')
        frag.write('vec2 envBRDF = texture(senvmapBrdf, vec2(roughness, 1.0 - dotNV)).xy;')

    if '_Irr' in wrd.world_defs:
        frag.add_include('std/shirr.glsl')
        frag.add_uniform('vec4 shirr[7]', link='_envmapIrradiance', included=True)
        frag.write('vec3 indirect = shIrradiance(n);')
        if '_EnvTex' in wrd.world_defs:
            frag.write('indirect /= PI;')
        frag.write('indirect *= albedo;')
        if '_Rad' in wrd.world_defs:
            frag.add_uniform('sampler2D senvmapRadiance', link='_envmapRadiance')
            frag.add_uniform('int envmapNumMipmaps', link='_envmapNumMipmaps')
            frag.write('vec3 reflectionWorld = reflect(-vVec, n);')
            frag.write('float lod = getMipFromRoughness(roughness, envmapNumMipmaps);')
            frag.write('vec3 prefilteredColor = textureLod(senvmapRadiance, envMapEquirect(reflectionWorld), lod).rgb;')
            if '_EnvLDR' in wrd.world_defs:
                frag.write('prefilteredColor = pow(prefilteredColor, vec3(2.2));')
            frag.write('indirect += prefilteredColor * (f0 * envBRDF.x + envBRDF.y) * 1.5;')
        elif '_EnvCol' in wrd.world_defs:
            frag.add_uniform('vec3 backgroundCol', link='_backgroundCol')
            frag.write('indirect += backgroundCol * f0;')
    else:
        frag.write('vec3 indirect = albedo;')
    frag.write('indirect *= occlusion;')

    frag.add_uniform('float envmapStrength', link='_envmapStrength')
    frag.write('indirect *= envmapStrength;')

    if '_VoxelGI' in wrd.world_defs or '_VoxelAO' in wrd.world_defs:
        frag.add_include('std/conetrace.glsl')
        frag.add_uniform('sampler3D voxels')
        if '_VoxelGICam' in wrd.world_defs:
            frag.add_uniform('vec3 eyeSnap', link='_cameraPositionSnap')
            frag.write('vec3 voxpos = (wposition - eyeSnap) / voxelgiHalfExtents;')
        else:
            frag.write('vec3 voxpos = wposition / voxelgiHalfExtents;')
        if '_VoxelAO' in wrd.world_defs:
            frag.write('indirect *= vec3(1.0 - traceAO(voxpos, n, voxels));')
            # frag.write('indirect = vec3(1.0 - traceAO(voxpos, n, voxels));') # AO view
        else:
            frag.write('vec4 indirectDiffuse = traceDiffuse(voxpos, n, voxels);')
            frag.write('indirect = indirect * voxelgiEnv + vec3(indirectDiffuse.rgb * voxelgiDiff * basecol);')
            frag.write('if (specular > 0.0) {')
            frag.write('vec3 indirectSpecular = traceSpecular(voxels, voxpos, n, vVec, roughness);')
            frag.write('indirectSpecular *= f0 * envBRDF.x + envBRDF.y;')
            frag.write('indirect += indirectSpecular * voxelgiSpec * specular;')
            frag.write('}')
