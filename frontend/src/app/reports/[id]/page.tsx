import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-3xl font-bold">Report: {id}</h1>
          <p className="mt-2 text-muted-foreground">Detailed analysis report</p>
        </div>
        <Badge>Completed</Badge>
      </div>

      <Tabs defaultValue="overview" className="w-full">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="quant">Quantitative</TabsTrigger>
          <TabsTrigger value="news">News Sentiment</TabsTrigger>
          <TabsTrigger value="social">Social Sentiment</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Report Summary</CardTitle>
              <CardDescription>
                Overview of all analysis components
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Report data will be loaded from the backend API
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="quant" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Quantitative Analysis</CardTitle>
              <CardDescription>
                Technical indicators and price analysis
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Quantitative analysis data will be displayed here
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="news" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>News Sentiment Analysis</CardTitle>
              <CardDescription>
                Analysis of recent news articles
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                News sentiment data will be displayed here
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="social" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Social Media Sentiment</CardTitle>
              <CardDescription>
                Analysis of social media discussions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                Social sentiment data will be displayed here
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
