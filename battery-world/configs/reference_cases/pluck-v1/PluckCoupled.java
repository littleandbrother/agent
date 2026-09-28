import com.comsol.model.*;
import com.comsol.model.util.*;

/** Native 3D electromechanical candidate. Assumed PZT-5A; not an SMS replica. */
public class PluckCoupled {
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
    m=ModelUtil.create("Model");m.label("Pluck candidate: coupled PZT with circuit load");
    m.param().set("RL","100[kohm]");m.param().set("F0","1[mN]");
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
    m.study().create("stat");m.study("stat").create("s","Stationary");
    for(int mesh=0;mesh<2;mesh++) {
      m.component("comp1").mesh("mesh1").autoMeshSize(mesh==0?6:4);m.component("comp1").mesh("mesh1").run();
      m.study("stat").run();
      rows("static"+mesh,values("mx"+mesh,latest(),"MaxVolume",new String[]{"solid.disp","solid.mises"}));
    }
    m.study().create("eig");m.study("eig").create("e","Eigenfrequency");
    m.study("eig").feature("e").set("neigs",6);
    m.study("eig").feature("e").set("shift","15[Hz]");
    m.study("eig").feature("e").set("shiftactive",true);
    m.study("eig").feature("e").setSolveFor("/physics/solid",true);
    m.study("eig").feature("e").setSolveFor("/physics/es",false);
    m.study("eig").feature("e").setSolveFor("/physics/cir",false);
    m.study("eig").run();rows("eigen",values("ev",latest(),"EvalGlobal",new String[]{"solid.freq"}));
    String finaldata="";
    for(int load=0;load<2;load++) {
      m.param().set("RL",load==0?"100[kohm]":"1[Mohm]");
      String tag="frf"+load;m.study().create(tag);m.study(tag).create("f","Frequency");
      m.study(tag).feature("f").set("plist","range(5,2,45)");m.study(tag).run();finaldata=latest();
      rows(tag,values("voltage"+load,finaldata,"EvalGlobal",new String[]{"freq","abs(es.V0_1)","abs(es.V0_1)^2/(2*RL)"}));
      rows(tag+"mechanical",values("motion"+load,finaldata,"MaxVolume",new String[]{"solid.disp","solid.mises"}));
    }
    m.result().create("voltage","PlotGroup1D");m.result("voltage").set("data",finaldata);m.result("voltage").label("Native circuit terminal voltage — 1 mN force, assumed PZT-5A");
    m.result("voltage").create("global","Global");m.result("voltage").feature("global").set("expr",new String[]{"abs(es.V0_1)"});
    m.result().create("stress","PlotGroup3D");m.result("stress").set("data",finaldata);m.result("stress").label("Stress — assumed candidate, not measured");
    m.result("stress").create("surf","Surface");m.result("stress").feature("surf").set("expr","solid.mises");
    m.result("stress").feature("surf").create("def","Deform");
    m.result().create("displacement","PlotGroup3D");m.result("displacement").set("data",finaldata);
    m.result("displacement").create("surf","Surface");m.result("displacement").feature("surf").set("expr","solid.disp");
    System.out.println("BF_COMPLETE,PluckCoupled");return m;
  }
  public static void main(String[] args) throws Exception {run();}
}
