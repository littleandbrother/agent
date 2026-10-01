import com.comsol.model.*;
import com.comsol.model.util.*;

/** Native 3D electromechanical candidate. Assumed PZT-5A; not an SMS replica. */
public class DoorBeam {
  static Model m;
  static void box(String tag,int dim,String axis,String low,String high) {
    m.component("comp1").selection().create(tag,"Box");
    m.component("comp1").selection(tag).set("entitydim",dim);
    m.component("comp1").selection(tag).set("condition","inside");
    m.component("comp1").selection(tag).set(axis+"min",low);
    m.component("comp1").selection(tag).set(axis+"max",high);
  }
  static void block(String tag,String[] size,String[] pos) {
    m.component("comp1").geom("geom1").create(tag,"Block");
    m.component("comp1").geom("geom1").feature(tag).set("size",size);
    m.component("comp1").geom("geom1").feature(tag).set("pos",pos);
    m.component("comp1").geom("geom1").feature(tag).set("selresult","on");
  }
  static void elastic(String tag,String selection,String young,String poisson,String density) {
    m.component("comp1").material().create(tag,"Common");
    m.component("comp1").material(tag).selection().named(selection);
    m.component("comp1").material(tag).propertyGroup("def").set("youngsmodulus",new String[]{young});
    m.component("comp1").material(tag).propertyGroup("def").set("poissonsratio",new String[]{poisson});
    m.component("comp1").material(tag).propertyGroup("def").set("density",new String[]{density});
  }
  static String latest() {String[] tags=m.result().dataset().tags();return tags[tags.length-1];}
  static double[][] values(String tag,String dataset,String type,String[] expr) {
    m.result().numerical().create(tag,type);
    m.result().numerical(tag).set("data",dataset);
    if(!type.equals("EvalGlobal"))m.result().numerical(tag).selection().all();
    m.result().numerical(tag).set("expr",expr);
    return m.result().numerical(tag).getReal();
  }
  static void rows(String kind,double[][] data) {
    for(int n=0;n<data[0].length;n++) {
      String row="BF_DATA,"+kind;
      for(int j=0;j<data.length;j++)row+=","+data[j][n];
      System.out.println(row);
    }
  }
  public static Model run() throws Exception {
    m=ModelUtil.create("Model");m.label("D1 native beam: stiffness, eigenmodes and piezo coupling");
    m.param().set("RL","100[kohm]");m.param().set("F0","0.3[N]");
    m.component().create("comp1",true);m.component("comp1").geom().create("geom1",3);
    block("copper",new String[]{"96[mm]","10[mm]","0.53[mm]"},new String[]{"4[mm]","-5[mm]","-0.265[mm]"});
    block("pzt",new String[]{"50[mm]","8[mm]","0.3[mm]"},new String[]{"10[mm]","-4[mm]","0.265[mm]"});
    block("magnet",new String[]{"10[mm]","10[mm]","10[mm]"},new String[]{"95[mm]","-5[mm]","0.265[mm]"});
    m.component("comp1").geom("geom1").run();
    box("fixed",2,"x","3.99999[mm]","4.00001[mm]");
    box("top",2,"z","0.56499[mm]","0.56501[mm]");
    box("bottom",2,"z","0.26499[mm]","0.26501[mm]");
    m.component("comp1").selection("bottom").set("xmin","9.99999[mm]");
    m.component("comp1").selection("bottom").set("xmax","60.00001[mm]");
    m.component("comp1").selection("bottom").set("ymin","-4.00001[mm]");
    m.component("comp1").selection("bottom").set("ymax","4.00001[mm]");
    box("forceface",2,"z","10.26499[mm]","10.26501[mm]");
    for(String tag:new String[]{"fixed","top","bottom","forceface"}) {
      int n=m.component("comp1").selection(tag).entities(2).length;
      System.out.println("BF_SELECTION,"+tag+","+n);
      if(n!=1)throw new RuntimeException("SELECTION_INVALID:"+tag+":"+n);
    }
    m.component("comp1").material().insert("/Applications/COMSOL62/Multiphysics/data/comsol_piezo_lib.mph",new String[]{"lead_zirconate_titanate_(pzt-5a)"});
    String pztmat=m.component("comp1").material().tags()[0];
    m.component("comp1").material(pztmat).selection().named("geom1_pzt_dom");
    elastic("copper","geom1_copper_dom","110[GPa]","0.34","8960[kg/m^3]");
    elastic("magnet","geom1_magnet_dom","160[GPa]","0.25","7500[kg/m^3]");
    m.component("comp1").physics().create("solid","SolidMechanics","geom1");
    m.component("comp1").physics("solid").create("fix1","Fixed",2);
    m.component("comp1").physics("solid").feature("fix1").selection().named("fixed");
    m.component("comp1").physics("solid").create("pzm1","PiezoelectricMaterialModel",3);
    m.component("comp1").physics("solid").feature("pzm1").selection().named("geom1_pzt_dom");
    m.component("comp1").physics("solid").feature("pzm1").set("ConstitutiveRelation","StressCharge");
    m.component("comp1").physics("solid").create("load1","BoundaryLoad",2);
    m.component("comp1").physics("solid").feature("load1").selection().named("forceface");
    m.component("comp1").physics("solid").feature("load1").set("FperArea",new String[]{"0","0","F0/100[mm^2]"});
    m.component("comp1").physics().create("es","Electrostatics","geom1");
    m.component("comp1").physics("es").selection().named("geom1_pzt_dom");
    m.component("comp1").physics("es").create("ccnp1","ChargeConservationPiezo",3);
    m.component("comp1").physics("es").feature("ccnp1").selection().named("geom1_pzt_dom");
    m.component("comp1").physics("es").create("gnd1","Ground",2);
    m.component("comp1").physics("es").feature("gnd1").selection().named("bottom");
    m.component("comp1").physics("es").create("term1","Terminal",2);
    m.component("comp1").physics("es").feature("term1").selection().named("top");
    m.component("comp1").physics("es").feature("term1").set("TerminalType","Circuit");
    m.component("comp1").physics().create("cir","Circuit","geom1");
    m.component("comp1").physics("cir").create("R1","Resistor");
    m.component("comp1").physics("cir").feature("R1").set("R","RL");
    m.component("comp1").physics("cir").feature("R1").set("Connections",new String[]{"0","1"});
    m.component("comp1").physics("cir").create("termI","ModelTerminalIV");
    m.component("comp1").physics("cir").feature("termI").set("Connections","1");
    m.component("comp1").physics("cir").feature("termI").set("V_src","root.comp1.es.V0_1");
    m.component("comp1").multiphysics().create("pze1","PiezoelectricEffect",3);
    m.component("comp1").multiphysics("pze1").set("Electrostatics_physics","es");
    m.component("comp1").multiphysics("pze1").set("InitializePiezoCoupling","1");
    m.component("comp1").mesh().create("mesh1");

    m.component("comp1").cpl().create("tipavg","Average");m.component("comp1").cpl("tipavg").selection().named("forceface");
    m.study().create("stat");m.study("stat").create("s","Stationary");
    for(int mesh:new int[]{6,4,3}) {
      m.component("comp1").mesh("mesh1").autoMeshSize(mesh);m.component("comp1").mesh("mesh1").run();m.study("stat").run();
      rows("static"+mesh,values("mx"+mesh,latest(),"MaxVolume",new String[]{"solid.disp","solid.mises"}));
      rows("tip"+mesh,values("tp"+mesh,latest(),"EvalGlobal",new String[]{"comp1.tipavg(w)"}));
    }
    String staticdata=latest();
    for(String field:new String[]{"solid.mises","solid.disp"}) {
      String tag=field.equals("solid.mises")?"stress":field.equals("solid.disp")?"displacement":"potential";
      m.result().create(tag,"PlotGroup3D");m.result(tag).set("data",staticdata);m.result(tag).label("D1 / 0.3 N transverse static load / "+field);
      m.result(tag).create("surf","Surface");m.result(tag).feature("surf").set("expr",field);
      if(tag.equals("potential"))m.result(tag).feature("surf").selection().named("top");
      m.result(tag).run();
      for(String type:new String[]{"png","gltf"})try {
        String exp=tag+type;m.result().export().create(exp,tag,"Image");m.result().export(exp).set("imagetype",type);
        m.result().export(exp).set(type.equals("png")?"pngfilename":"gltffilename","__OUTPUT__/"+tag+(type.equals("png")?".png":".glb"));
        m.result().export(exp).set("size","manualweb");m.result().export(exp).set("unit","px");m.result().export(exp).set("width",1600);m.result().export(exp).set("height",900);
        m.result().export(exp).set("zoomextents","on");m.result().export(exp).run();
      }catch(Exception e){System.out.println("BF_EXPORT_ERROR,"+tag+","+type+","+e.toString());}
    }
    m.study().create("eig");m.study("eig").create("e","Eigenfrequency");m.study("eig").feature("e").set("neigs",6);m.study("eig").feature("e").set("shift","15[Hz]");m.study("eig").feature("e").set("shiftactive",true);
    m.study("eig").feature("e").setSolveFor("/physics/solid",true);m.study("eig").feature("e").setSolveFor("/physics/es",false);m.study("eig").feature("e").setSolveFor("/physics/cir",false);
    m.study("eig").run();rows("eigen",values("ev",latest(),"EvalGlobal",new String[]{"solid.freq"}));
    // Reciprocal DC actuation derives effective coupling. Terminal no longer connected to circuit.
    m.param().set("F0","0[N]");m.component("comp1").physics("es").feature("term1").set("TerminalType","Voltage");m.component("comp1").physics("es").feature("term1").set("V0","1[V]");
    m.study().create("act");m.study("act").create("s","Stationary");m.study("act").feature("s").setSolveFor("/physics/cir",false);
    m.component("comp1").physics("cir").active(false);m.study("act").run();
    rows("actuation",values("actv",latest(),"EvalGlobal",new String[]{"comp1.tipavg(w)","es.Q0_1"}));
    System.out.println("BF_COMPLETE,DoorBeam");return m;
  }
  public static void main(String[] args)throws Exception{run();}
}
