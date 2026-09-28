import com.comsol.model.*;
import com.comsol.model.util.*;

/** A declared pulse verifies coupled transient response, not magnet release. */
public class PluckTransient {
  static Model m;
  static void output(String tag,String dataset,String type,String[] expr) {
    m.result().numerical().create(tag,type);m.result().numerical(tag).set("data",dataset);
    if(!type.equals("EvalGlobal"))m.result().numerical(tag).selection().all();
    m.result().numerical(tag).set("expr",expr);
    double[][] a=m.result().numerical(tag).getReal();
    for(int n=0;n<a[0].length;n++) {String row="BF_TRANSIENT,"+tag;for(double[] v:a)row+=","+v[n];System.out.println(row);}
  }
  public static Model run() throws Exception {
    m=ModelUtil.load("Model","__BASE__");m.label("Pluck candidate — controlled pulse transient");
    m.param().set("RL","100[kohm]");
    m.component("comp1").cpl().create("tipavg","Average");
    m.component("comp1").cpl("tipavg").selection().named("forceface");
    m.component("comp1").physics("solid").feature("load1").set("FperArea",new String[]{"0","0","10[mN]*exp(-((t-0.02[s])/0.005[s])^2)/100[mm^2]"});
    m.study().create("pulse");m.study("pulse").create("t","Transient");
    m.study("pulse").feature("t").set("tlist","range(0,0.001,0.4)");
    m.study("pulse").feature("t").set("rtol","1e-4");
    m.study("pulse").run();
    String[] datasets=m.result().dataset().tags();String dataset=datasets[datasets.length-1];
    output("signal",dataset,"EvalGlobal",new String[]{"t","es.V0_1","es.V0_1^2/RL","comp1.tipavg(w)"});
    output("field",dataset,"MaxVolume",new String[]{"solid.disp","solid.mises"});
    m.result().create("pulsevoltage","PlotGroup1D");m.result("pulsevoltage").set("data",dataset);m.result("pulsevoltage").label("10 mN Gaussian test pulse — native coupled output");
    m.result("pulsevoltage").create("g","Global");m.result("pulsevoltage").feature("g").set("expr",new String[]{"es.V0_1"});
    m.result().create("pulsestress","PlotGroup3D");m.result("pulsestress").set("data",dataset);
    m.result("pulsestress").create("s","Surface");m.result("pulsestress").feature("s").set("expr","solid.mises");
    m.result("pulsestress").feature("s").create("d","Deform");
    System.out.println("BF_TRANSIENT_COMPLETE");return m;
  }
  public static void main(String[] args) throws Exception {run();}
}
