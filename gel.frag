#version 120
varying vec2 uv;
uniform float uPhase,uDeform,uGreen,uViolet,uDepth,uScale,uGlow,uGloss;
uniform vec2 uResolution;
mat3 rotY(float a){float s=sin(a),c=cos(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
mat3 rotX(float a){float s=sin(a),c=cos(a);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
float field(vec3 p){
 vec3 q=rotY(uPhase*.22)*rotX(.27*sin(uPhase*.19))*p;
 // Six intersecting, slowly drifting spatial waves, rather than fixed lobes.
 return .26*sin(dot(q,vec3(2.9,1.2,.8))+uPhase*.44)
       +.23*sin(dot(q,vec3(-1.3,2.7,1.4))-uPhase*.37+1.8)
       +.19*sin(dot(q,vec3(.7,-1.5,3.1))+uPhase*.29+3.2)
       +.14*sin(dot(q,vec3(3.6,1.7,-2.1))-uPhase*.23+4.7)
       +.11*sin(dot(q,vec3(-2.1,3.8,1.3))+uPhase*.41+2.5)
       +.07*sin(dot(q,vec3(1.8,-2.9,3.7))-uPhase*.17+.9);
}
float sdf(vec3 p){return length(p)-1.-uDeform*field(normalize(p));}
vec3 normalAt(vec3 p){vec2 e=vec2(.002,0.);return normalize(vec3(sdf(p+e.xyy)-sdf(p-e.xyy),sdf(p+e.yxy)-sdf(p-e.yxy),sdf(p+e.yyx)-sdf(p-e.yyx)));}
vec3 environment(vec3 d){
 // Retuned 2026-10-10: a window-shaped softbox replaces the ceiling band, whose
 // reflection read as a ring at small sizes. Previous version in backups/before-gel-retuned-20261010.
 float m=max(abs(d.x+.12)/.30,abs(d.y-.56)/.15);
 float box=mix(exp(-pow(m,4.)*1.4),1.-smoothstep(.92,1.,m),uGloss*.7);
 float strip=exp(-pow((d.x+.78)/mix(.065,.02,uGloss),2.))*smoothstep(-.5,.3,d.y)*.8;
 float floorLight=exp(-pow((d.y+.73)/.16,2.));
 // Red gel 2026-10-11: warm floor bounce while listening, neutral during cleanup.
 vec3 floorCol=mix(vec3(.6,.14,.05),vec3(.32,.33,.36),uGreen);
 return vec3(.02,.025,.04)+vec3(.05,.06,.1)*(.5+.5*d.y)+vec3(3.4,3.6,4.)*box+vec3(1.3,1.7,2.5)*strip+floorCol*floorLight;
}
void main(){
 if(uScale<.001){gl_FragColor=vec4(0.);return;}
 vec2 xy=uv*1.6/uScale;
 vec3 ro=vec3(xy,3.),rd=vec3(0.,0.,-1.);
 float t=0.;bool hit=false;vec3 p;
 for(int i=0;i<64;i++){p=ro+rd*t;float d=sdf(p);if(d<.0012){hit=true;break;}t+=max(.0004,d*.67);if(t>5.)break;}
 // Red-orange halo while listening; almost none while cleaning up.
 vec3 glowColor=mix(vec3(1.,.24,.10),vec3(.85,.9,1.),uGreen);
 float glowAmt=uGlow*mix(1.,.25,uGreen);
 if(!hit){
   // A quiet, steady halo identifies accepted speech; no idle heartbeat.
   float edge=max(0.,length(xy)-1.-uDeform*field(normalize(vec3(xy,.08))));
   float halo=exp(-edge/.115)*(1.-smoothstep(.04,.52,edge))*glowAmt*.62;
   gl_FragColor=vec4(glowColor,halo);return;
 }
 vec3 n=normalAt(p),v=-rd,refl=reflect(rd,n);
 float facing=clamp(dot(n,v),0.,1.),fresnel=pow(1.-facing,3.);
 // Listening: crimson body, orange-red drifting zone, thin amber rim glint.
 // Cleanup: colourless glass. Previous blue/violet/green palette in backups/before-red-gel-20261011.
 vec3 blue=vec3(.90,.01,.05),violet=vec3(.97,.12,.03),red=vec3(1.,.50,.08);
 vec3 green=vec3(.93,.95,.98),warm=vec3(.97,.97,1.);
 float zone=dot(rotY(uPhase*.09)*n,normalize(vec3(.9,-.35,.3)));
 float violetWeight=exp(-pow((zone-.36)/.45,2.))*uViolet;
 vec3 cool=mix(blue,violet,violetWeight);
 cool=mix(cool,red,smoothstep(.57,1.,zone)*.42);
 vec3 polish=mix(green,warm,smoothstep(.42,1.,zone)*.85);
 vec3 tint=mix(cool,polish,uGreen);
 float tintAmt=mix(1.,.18,uGreen);
 // Body opacity: 25% listening, 10% cleanup (owner, 2026-10-12; was 0%).
 float body=mix(.25,.10,uGreen);
 vec3 refraction=environment(refract(rd,n,1./1.43));
 float thickness=2.*sqrt(max(.02,1.-min(.98,dot(xy,xy))));
 vec3 absorption=exp(-(vec3(1.)-tint)*thickness*.4);
 // Stained glass: the body shows its own tint instead of a fake dark room, which read as grey smoke on white pages.
 vec3 col=tint*(.62+.5*fresnel)*tintAmt+vec3(.9,.92,.95)*.04*(1.-tintAmt);
 col=mix(col,col*.75+refraction*absorption*.12,body*.6);
 vec3 reflections=environment(refl);
 col+=max(reflections-vec3(.15),0.)*(.17+.6*fresnel)*(.65+.6*uDepth);
 vec3 light=normalize(vec3(-.55,.75,1.));
 float spec=pow(max(0.,dot(n,normalize(v+light))),mix(95.,420.,uGloss));
 float broad=pow(max(0.,dot(n,normalize(v+normalize(vec3(.5,-.7,.5))))),18.);
 float caustic=exp(-pow((facing-.35)/.13,2.))*(1.-smoothstep(-.8,.2,n.y));
 col+=vec3(1.,1.,1.)*spec*mix(1.7,4.2,uGloss) + (tint*broad*.38 + tint*caustic*.75)*tintAmt;
 col+=glowColor*glowAmt*pow(1.-facing,2.)*.5;
 // Filmic roll-off and fine dithering preserve smooth highlight gradients.
 col=col/(vec3(.6)+col);
 col=pow(col,vec3(1./1.65));
 float noise=fract(sin(dot(gl_FragCoord.xy,vec2(12.9898,78.233)))*43758.5453)-.5;
 col+=noise/255.;
 float highlight=clamp(max(reflections.r,max(reflections.g,reflections.b))*.35,0.,1.);
 float alpha=clamp(mix(.02,.60,body)+.60*fresnel*mix(1.,.6,uGreen)+.55*spec+.22*caustic*tintAmt+.16*uDepth*tintAmt+highlight*uGloss*.55,0.,.99);
 gl_FragColor=vec4(col,alpha);
}