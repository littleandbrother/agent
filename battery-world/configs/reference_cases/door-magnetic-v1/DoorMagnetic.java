import com.comsol.model.*;
import com.comsol.model.util.*;
/** Native finite-domain magnetostatics. Nominal NdFeB, no measured calibration. */
public class DoorMagnetic {
 static Model m;
 static void block(String tag,String[] size,String[] pos){
  m.component("c").geom("g").create(tag,"Block");
  m.component("c").geom("g").feature(tag).set("size",size);
  m.component("c").geom("g").feature(tag).set("pos",pos);
  m.component("c").geom("g").feature(tag).set("selresult","on");
 }
 static void export(String tag,String filename,String type){
  m.result().export().create(tag,"field","Image");
  m.result().export(tag).set("imagetype",type);
  m.result().export(tag).set(type.equals("gltf")?"gltffilename":"pngfilename","__OUTPUT__/"+filename);
  m.result().export(tag).set("size","manualweb");
  m.result().export(tag).set("unit","px");
  m.result().export(tag).set("width",1600);m.result().export(tag).set("height",1000);
  m.result().export(tag).set("zoomextents","on");m.result().export(tag).run();
 }
 public static Model run() throws Exception {
  m=ModelUtil.create("Model");m.label("D2 driver field / rigid uniformly magnetized tip force projection");
  m.param().set("dz","15[mm]");m.param().set("dx","48[mm]");m.param().set("Rair","150[mm]");
  m.component().create("c",true);m.component("c").geom().create("g",3);
  m.component("c").geom("g").create("air","Sphere");m.component("c").geom("g").feature("air").set("r","Rair");
  block("tip",new String[]{"10[mm]","10[mm]","10[mm]"},new String[]{"-5[mm]","-5[mm]","-5[mm]"});
  block("driver",new String[]{"20[mm]","20[mm]","20[mm]"},new String[]{"dx-10[mm]","-10[mm]","dz-10[mm]"});
  m.component("c").geom("g").run();
  m.component("c").physics().create("mfnc","MagnetostaticsNoCurrents","g");
  m.component("c").physics("mfnc").feature("mfc1").set("mur_mat","userdef");m.component("c").physics("mfnc").feature("mfc1").set("mur",1);
  for(String tag:new String[]{"tip","driver"}) {
   m.component("c").physics("mfnc").create(tag,"MagneticFluxConservation",3);
   m.component("c").physics("mfnc").feature(tag).selection().named("g_"+tag+"_dom");
   m.component("c").physics("mfnc").feature(tag).set("ConstitutiveRelationBH","RemanentFluxDensity");
   m.component("c").physics("mfnc").feature(tag).set("mur_crel_BH_RemanentFluxDensity_mat","userdef");
   m.component("c").physics("mfnc").feature(tag).set("mur_crel_BH_RemanentFluxDensity",1.05);
   m.component("c").physics("mfnc").feature(tag).set("normBr_crel_BH_RemanentFluxDensity_mat","userdef");
   m.component("c").physics("mfnc").feature(tag).set("normBr_crel_BH_RemanentFluxDensity","1.25[T]");
   m.component("c").physics("mfnc").feature(tag).set("e_crel_BH_RemanentFluxDensity",new String[]{"1","0","0"});
  }
  m.component("c").physics("mfnc").create("fc","ForceCalculation",3);
  m.component("c").physics("mfnc").feature("fc").selection().named("g_tip_dom");
  m.component("c").physics("mfnc").feature("fc").set("ForceName","tip");
  m.component("c").selection().create("gauge","Box");m.component("c").selection("gauge").set("entitydim",0);m.component("c").selection("gauge").set("zmin","Rair-1[um]");m.component("c").selection("gauge").set("zmax","Rair+1[um]");
  m.component("c").physics("mfnc").create("gauge","ZeroMagneticScalarPotential",0);m.component("c").physics("mfnc").feature("gauge").selection().named("gauge");
  m.component("c").mesh().create("mesh");
  m.study().create("s");m.study("s").create("stat","Stationary");
  m.study("s").createAutoSequences("all");m.sol("sol1").feature("s1").feature("fc1").set("linsolver","dDef");
  m.result().numerical().create("force","EvalGlobal");
  m.component("c").physics("mfnc").feature("tip").set("normBr_crel_BH_RemanentFluxDensity","0[T]");
  m.component("c").physics("mfnc").feature("tip").set("mur_crel_BH_RemanentFluxDensity",1);
  m.component("c").cpl().create("probe","Integration");m.component("c").cpl("probe").selection().named("g_tip_dom");
  m.result().numerical("force").set("expr",new String[]{"c.probe(1.25[T]/mu0_const*d(mfnc.Bx,x))","c.probe(1.25[T]/mu0_const*d(mfnc.Bx,z))"});
  for(int mesh:new int[]{3,2}) {
   m.component("c").mesh("mesh").autoMeshSize(mesh);
   for(int z:new int[]{0,20,45}) {
    m.param().set("dz",z+"[mm]");m.component("c").geom("g").run();m.component("c").mesh("mesh").run();m.sol("sol1").runAll();
    String[] datasets=m.result().dataset().tags();m.result().numerical("force").set("data",datasets[datasets.length-1]);
    double[][] v=m.result().numerical("force").getReal();System.out.println("BF_DATA,force,"+mesh+","+z+","+v[0][0]+","+v[1][0]);
   }
  }
  m.param().set("dz","15[mm]");m.component("c").geom("g").run();m.component("c").mesh("mesh").run();m.sol("sol1").runAll();
  m.result().create("field","PlotGroup3D");m.result("field").label("Magnetic flux density / T | D2 nominal NdFeB | dz 15 mm");
  m.result("field").create("slice","Slice");m.result("field").feature("slice").set("expr","mfnc.normB");
  m.result("field").feature("slice").set("quickplane","zx");m.result("field").feature("slice").set("quickynumber",1);

  m.result("field").run();
  try {export("png","magnetic-flux.png","png");}catch(Exception e){System.out.println("BF_EXPORT_ERROR,"+e.toString());}
  try {export("glb","magnetic-flux.glb","gltf");}catch(Exception e){System.out.println("BF_EXPORT_ERROR,"+e.toString());}
  System.out.println("BF_COMPLETE,DoorMagnetic");return m;
 }
 public static void main(String[] args)throws Exception{run();}
}
