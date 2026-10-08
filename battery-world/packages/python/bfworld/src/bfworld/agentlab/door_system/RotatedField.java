import com.comsol.model.*;
import com.comsol.model.util.*;
/** Independent FEM anchor of rotating uniform hard magnets, mu_r exactly 1.
 * Tip is a neutral integration region; no self force. Not measured calibration.
 */
public class RotatedField {
 static Model m;
 static void block(String tag,String[] size,String[] pos){
  m.component("c").geom("g").create(tag,"Block");
  m.component("c").geom("g").feature(tag).set("size",size);
  m.component("c").geom("g").feature(tag).set("pos",pos);
  m.component("c").geom("g").feature(tag).set("selresult","on");
 }
 public static Model run() throws Exception {
  m=ModelUtil.create("Model");m.label("D4 rotated driver / neutral-tip field-gradient anchor");
  m.param().set("dx","__DX__[m]");m.param().set("dz","__DZ__[m]");
  m.param().set("angle","__ANGLE__[rad]");m.param().set("Rair","__RAIR__[mm]");
  m.component().create("c",true);m.component("c").geom().create("g",3);
  m.component("c").geom("g").create("air","Sphere");m.component("c").geom("g").feature("air").set("r","Rair");
  block("tip",new String[]{"10[mm]","10[mm]","10[mm]"},new String[]{"-5[mm]","-5[mm]","-5[mm]"});
  block("driver",new String[]{"20[mm]","20[mm]","20[mm]"},new String[]{"dx-10[mm]","-10[mm]","dz-10[mm]"});
  m.component("c").geom("g").create("turn","Rotate");
  m.component("c").geom("g").feature("turn").selection("input").set(new String[]{"driver"});
  m.component("c").geom("g").feature("turn").set("axis",new String[]{"0","1","0"});
  m.component("c").geom("g").feature("turn").set("pos",new String[]{"dx","0","dz"});
  m.component("c").geom("g").feature("turn").set("rot","angle");
  m.component("c").geom("g").feature("turn").set("selresult","on");
  m.component("c").geom("g").run();
  m.component("c").physics().create("mfnc","MagnetostaticsNoCurrents","g");
  m.component("c").physics("mfnc").feature("mfc1").set("mur_mat","userdef");
  m.component("c").physics("mfnc").feature("mfc1").set("mur",1);
  m.component("c").physics("mfnc").create("driver","MagneticFluxConservation",3);
  m.component("c").physics("mfnc").feature("driver").selection().named("g_turn_dom");
  m.component("c").physics("mfnc").feature("driver").set("ConstitutiveRelationBH","RemanentFluxDensity");
  m.component("c").physics("mfnc").feature("driver").set("mur_crel_BH_RemanentFluxDensity_mat","userdef");
  m.component("c").physics("mfnc").feature("driver").set("mur_crel_BH_RemanentFluxDensity",1);
  m.component("c").physics("mfnc").feature("driver").set("normBr_crel_BH_RemanentFluxDensity_mat","userdef");
  m.component("c").physics("mfnc").feature("driver").set("normBr_crel_BH_RemanentFluxDensity","1.25[T]");
  m.component("c").physics("mfnc").feature("driver").set("e_crel_BH_RemanentFluxDensity",new String[]{"__POLARITY__*cos(angle)","0","-__POLARITY__*sin(angle)"});
  m.component("c").selection().create("gauge","Box");
  m.component("c").selection("gauge").set("entitydim",0);
  m.component("c").selection("gauge").set("zmin","Rair-1[um]");m.component("c").selection("gauge").set("zmax","Rair+1[um]");
  m.component("c").physics("mfnc").create("gauge","ZeroMagneticScalarPotential",0);
  m.component("c").physics("mfnc").feature("gauge").selection().named("gauge");
  m.component("c").mesh().create("mesh");m.component("c").mesh("mesh").autoMeshSize(3);
  m.component("c").mesh("mesh").create("tipSize","Size");
  m.component("c").mesh("mesh").feature("tipSize").selection().named("g_tip_dom");
  m.component("c").mesh("mesh").feature("tipSize").set("custom","on");
  m.component("c").mesh("mesh").feature("tipSize").set("hmin","0.2[mm]");
  m.component("c").mesh("mesh").feature("tipSize").set("hgrad",1.3);
  m.component("c").mesh("mesh").create("tet","FreeTet");
  m.study().create("s");m.study("s").create("stat","Stationary");
  m.study("s").createAutoSequences("all");m.sol("sol1").feature("s1").feature("fc1").set("linsolver","dDef");
  m.component("c").cpl().create("probe","Integration");m.component("c").cpl("probe").selection().named("g_tip_dom");
  m.result().numerical().create("force","EvalGlobal");
  m.result().numerical("force").set("expr",new String[]{"c.probe(1.25[T]/mu0_const*d(mfnc.Bx,x))","c.probe(1.25[T]/mu0_const*d(mfnc.Bx,z))"});
  int index=0;
  for(double h:new double[]{1.5,1.0,0.7}) {
   m.component("c").mesh("mesh").feature("tipSize").set("hmax",h+"[mm]");
   m.component("c").mesh("mesh").run();m.sol("sol1").runAll();
   String[] datasets=m.result().dataset().tags();m.result().numerical("force").set("data",datasets[datasets.length-1]);
   double[][] v=m.result().numerical("force").getReal();System.out.println("BF_DATA,force,"+h+","+v[0][0]+","+v[1][0]);
   m.param().set("BF_fx"+index,v[0][0]+"[N]");m.param().set("BF_fz"+index,v[1][0]+"[N]");index++;
  }
  m.result().create("field","PlotGroup3D");m.result("field").label("D4 independent rotated FEM | magnetic flux density (T)");
  m.result("field").create("slice","Slice");m.result("field").feature("slice").set("expr","mfnc.normB");
  m.result("field").feature("slice").set("quickplane","zx");m.result("field").feature("slice").set("quickynumber",1);m.result("field").run();
  // Read solved values and export through the normal client API. Batch methods
  // retain their default filesystem restrictions; no global preference change.
  m.param().set("BF_complete","1");
  System.out.println("BF_COMPLETE,RotatedField");return m;
 }
 public static void main(String[] args)throws Exception {run();}
}
