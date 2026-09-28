import com.comsol.model.*;
import com.comsol.model.util.*;

/** Unit-aware static cantilever template, generated numeric parameters only. */
public class Cantilever {
  public static Model run() throws Exception {
    Model m = ModelUtil.create("Model");
    m.label("BF cantilever template");
    m.param().set("beam_L", "__L__[mm]");
    m.param().set("beam_b", "__B__[mm]");
    m.param().set("beam_t", "__H__[mm]");
    m.param().set("beam_E", "__E__[GPa]");
    m.param().set("beam_F", "__F__[N]");
    m.component().create("comp1", true);
    m.component("comp1").geom().create("geom1",3);
    m.component("comp1").geom("geom1").create("blk1","Block");
    m.component("comp1").geom("geom1").feature("blk1").set("size",new String[]{"beam_L","beam_b","beam_t"});
    m.component("comp1").geom("geom1").run();
    m.component("comp1").selection().create("root","Box");
    m.component("comp1").selection("root").set("entitydim",2);
    m.component("comp1").selection("root").set("condition","inside");
    m.component("comp1").selection("root").set("xmin","-1e-8");
    m.component("comp1").selection("root").set("xmax","1e-8");
    m.component("comp1").selection().create("tip","Box");
    m.component("comp1").selection("tip").set("entitydim",2);
    m.component("comp1").selection("tip").set("condition","inside");
    m.component("comp1").selection("tip").set("xmin","beam_L-1e-8");
    m.component("comp1").selection("tip").set("xmax","beam_L+1e-8");
    if(m.component("comp1").selection("root").entities(2).length!=1 || m.component("comp1").selection("tip").entities(2).length!=1)
      throw new RuntimeException("BOUNDARY_SELECTION_INVALID");
    m.component("comp1").material().create("mat1","Common");
    m.component("comp1").material("mat1").propertyGroup("def").set("youngsmodulus",new String[]{"beam_E"});
    m.component("comp1").material("mat1").propertyGroup("def").set("poissonsratio",new String[]{"0.3"});
    m.component("comp1").material("mat1").propertyGroup("def").set("density",new String[]{"7800[kg/m^3]"});
    m.component("comp1").physics().create("solid","SolidMechanics","geom1");
    m.component("comp1").physics("solid").create("fix1","Fixed",2);
    m.component("comp1").physics("solid").feature("fix1").selection().named("root");
    m.component("comp1").physics("solid").create("load1","BoundaryLoad",2);
    m.component("comp1").physics("solid").feature("load1").selection().named("tip");
    m.component("comp1").physics("solid").feature("load1").set("FperArea",new String[]{"0","0","-beam_F/(beam_b*beam_t)"});
    m.component("comp1").mesh().create("mesh1");
    m.study().create("std1"); m.study("std1").create("stat","Stationary");
    double[] displacement=new double[2]; double[] stress=new double[2];
    for(int i=0;i<2;i++) {
      m.component("comp1").mesh("mesh1").autoMeshSize(i==0?5:3);
      m.component("comp1").mesh("mesh1").run();
      m.study("std1").run();
      String tag="max"+i;
      m.result().numerical().create(tag,"MaxVolume");
      m.result().numerical(tag).selection().all();
      m.result().numerical(tag).set("expr",new String[]{"solid.disp","solid.mises"});
      double[][] values=m.result().numerical(tag).getReal();
      displacement[i]=values[0][0];stress[i]=values[1][0];
    }
    System.out.println("BF_METRICS,coarse,"+displacement[0]+","+stress[0]);
    System.out.println("BF_METRICS,fine,"+displacement[1]+","+stress[1]);
    // The batch runner saves the native model. Do not relax Java filesystem preferences.
    return m;
  }
  public static void main(String[] args) throws Exception { run(); }
}
